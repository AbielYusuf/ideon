"""Shared test helpers. Gemini is always faked; no live key is required."""

from __future__ import annotations

import tempfile
from contextlib import closing
from pathlib import Path

import auth_store
import database
from assessment_models import (
    AssessmentAnalysis,
    AssessmentNarrative,
    RefinedIdea,
)
from auth import hash_password
from gemini_service import ScoringPayload

TEST_PASSWORD = "CorrectHorseBattery9"

ANALYSIS = AssessmentAnalysis(
    summary="A small but plausible idea.",
    key_strengths=["Clear audience"],
    key_weaknesses=["No cost estimate"],
    missing_information=["Expected budget"],
    critical_assumptions=["A small team is available"],
    uncertainty_notes=["Demand is not measured"],
    clarifying_questions=["Who is the first customer?", "What is the budget?"],
    proposed_refined_title="Refined portal",
    proposed_refined_description="A refined description with clearer scope.",
)

NARRATIVE = AssessmentNarrative(
    summary="The confirmed idea is credible.",
    key_strengths=["Clear audience"],
    key_weaknesses=["No cost estimate"],
    missing_information=["Expected budget"],
    critical_assumptions=["A small team is available"],
    uncertainty_notes=["Demand is not measured"],
)

CRITERIA = [
    {
        "criterion": "Impact",
        "score": 90,
        "reasoning": "High reach.",
        "evidence": "The idea names a broad audience.",
        "assumptions": "The audience is reachable.",
    },
    {
        "criterion": "Feasibility",
        "score": 85,
        "reasoning": "Simple build.",
        "evidence": "The scope is narrow.",
        "assumptions": "The team has the needed skills.",
    },
    {
        "criterion": "Efficiency & Cost",
        "score": 80,
        "reasoning": "Low operating cost.",
        "evidence": "No hardware is required.",
        "assumptions": "Hosting stays small.",
    },
    {
        "criterion": "Risk Control",
        "score": 75,
        "reasoning": "Some risks remain.",
        "evidence": "The idea lists mitigations.",
        "assumptions": "The mitigations are followed.",
    },
    {
        "criterion": "Goal Alignment",
        "score": 70,
        "reasoning": "Mostly aligned.",
        "evidence": "The idea targets the stated goal.",
        "assumptions": "The goal stays unchanged.",
    },
]


def fresh_database(case) -> None:
    """Point the shared database module at a disposable database."""
    temporary = tempfile.TemporaryDirectory()
    case.addCleanup(temporary.cleanup)
    database.DATABASE_PATH = Path(temporary.name) / "ideon.db"
    database.initialize_database()


def insert_idea(
    title: str = "Test idea",
    description: str = "Test description",
    user_id: int | None = None,
) -> int:
    with closing(database.get_connection()) as connection:
        with connection:
            cursor = connection.execute(
                "INSERT INTO ideas (user_id, title, description) VALUES (?, ?, ?)",
                (user_id, title, description),
            )
            return int(cursor.lastrowid)


def create_user(
    username: str = "test-user",
    *,
    email: str | None = None,
    password: str = TEST_PASSWORD,
    role: str = "user",
) -> dict:
    """Create an account directly, bypassing the registration endpoint."""
    user = auth_store.create_user(
        username=username,
        email=email or f"{username}@example.com",
        password_hash=hash_password(password),
        role=role,
    )
    with closing(database.get_connection()) as connection:
        with connection:
            connection.executemany(
                """
                INSERT INTO web_shortcuts (user_id, name, url, category)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (user["id"], name, url, category)
                    for name, url, category in database.DEFAULT_SHORTCUTS
                ],
            )
    return user


def login_client(client, email: str, password: str = TEST_PASSWORD) -> dict:
    """Log the TestClient in and arm its CSRF header for later mutations."""
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    if response.status_code != 200:
        raise AssertionError(
            f"Login failed with {response.status_code}: {response.text}"
        )
    csrf = client.cookies.get("ideon_csrf")
    if not csrf:
        raise AssertionError("Login did not set the CSRF cookie.")
    client.headers.update({"X-CSRF-Token": csrf})
    return response.json()


def authenticated_user(
    client,
    username: str = "test-user",
    *,
    email: str | None = None,
    role: str = "user",
) -> dict:
    """Create an account and log the supplied TestClient in as it."""
    user = create_user(username=username, email=email, role=role)
    login_client(client, user["email"])
    return user


class FakeGemini:
    """Stands in for GeminiService in service and API tests."""

    def __init__(
        self,
        *,
        analysis: AssessmentAnalysis | None = None,
        refined: RefinedIdea | None = None,
        criteria: list[dict] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.analysis = analysis or ANALYSIS
        self.refined = refined or RefinedIdea(
            title="Refined portal", description="Refined portal description."
        )
        self.criteria = criteria or CRITERIA
        self.error = error
        self.prepare_calls = []
        self.refine_calls = []
        self.score_calls = []

    def prepare(self, idea):
        self.prepare_calls.append(idea)
        if self.error:
            raise self.error
        return self.analysis

    def refine(self, idea, analysis, answers):
        self.refine_calls.append((idea, analysis, answers))
        if self.error:
            raise self.error
        return self.refined

    def score(self, idea, analysis, confirmed_title, confirmed_description):
        self.score_calls.append(
            (idea, analysis, confirmed_title, confirmed_description)
        )
        if self.error:
            raise self.error
        return ScoringPayload(narrative=NARRATIVE, criteria=self.criteria)
