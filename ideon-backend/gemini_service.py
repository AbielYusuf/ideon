"""Isolated Gemini integration for the Ideon assessment workflow.

FastAPI route handlers must call this service through ``assessment_service``,
never the Gemini SDK directly.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import ValidationError

from assessment_models import (
    AssessmentAnalysis,
    AssessmentNarrative,
    IdeaSnapshot,
    RefinedIdea,
)
from improvement_models import GeneratedProposalContent
from scoring import RUBRIC

load_dotenv(dotenv_path=Path(__file__).resolve().with_name(".env"))

DEFAULT_TIMEOUT_MS = 30_000

# Shared by every Gemini workflow so response language never varies by stage.
LANGUAGE_INSTRUCTION = """Language requirement (mandatory):
- Write every user-facing natural-language value in Bahasa Indonesia.
- This applies regardless of the language of the original idea or clarification answers.
- Cover all explanatory text: summaries, strengths, weaknesses, missing information, assumptions, uncertainty notes, recommendations, clarifying questions, refined titles and descriptions, and criterion reasoning and evidence.
- Do not translate the user's original idea text; quote it as provided.
- Technical terms, proper nouns, product names, programming terminology, and commonly used English technical expressions may remain in English.
- Keep JSON keys, enums, and the response structure exactly as specified."""


class GeminiError(RuntimeError):
    """Base class for Gemini service failures."""


class GeminiConfigurationError(GeminiError):
    """Gemini environment configuration is missing or invalid."""


class GeminiAuthenticationError(GeminiError):
    """Gemini rejected the configured API key."""


class GeminiTimeoutError(GeminiError):
    """The Gemini request timed out."""


class GeminiUnavailableError(GeminiError):
    """Gemini is temporarily unavailable or the request failed at the network."""


class GeminiResponseError(GeminiError):
    """Gemini returned malformed or incomplete JSON."""


@dataclass(frozen=True)
class GeminiConfig:
    api_key: str
    model: str


@dataclass(frozen=True)
class ScoringPayload:
    narrative: AssessmentNarrative
    criteria: list[dict[str, Any]]


def load_config() -> GeminiConfig:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    model = os.environ.get("GEMINI_MODEL", "").strip()
    missing = [
        name
        for name, value in (("GEMINI_API_KEY", api_key), ("GEMINI_MODEL", model))
        if not value
    ]

    if missing:
        raise GeminiConfigurationError(
            "Gemini is not configured. Add "
            + " and ".join(missing)
            + " to the backend .env file."
        )

    return GeminiConfig(api_key=api_key, model=model)


def _format_weight(weight: float) -> str:
    return f"{round(weight * 100, 2):g}%"


def _rubric_lines() -> str:
    return "\n".join(
        f"- {criterion.name}: {_format_weight(criterion.weight)}"
        for criterion in RUBRIC
    )


def _criteria_json_names() -> str:
    return "\n".join(f"  - {criterion.name}" for criterion in RUBRIC)


def _strip_code_fence(text: str) -> str:
    text = text.strip()

    if not text.startswith("```"):
        return text

    lines = text.splitlines()

    if lines and lines[0].startswith("```"):
        lines = lines[1:]

    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]

    return "\n".join(lines).strip()


def parse_json_object(text: str | None) -> dict[str, Any]:
    """Parse a JSON object from a model response, tolerating code fences."""
    if not text or not text.strip():
        raise GeminiResponseError("Gemini returned an empty response.")

    candidate = _strip_code_fence(text)

    for value in (candidate, _object_slice(candidate)):
        if value is None:
            continue

        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            continue

        if isinstance(parsed, dict):
            return parsed

    raise GeminiResponseError("Gemini returned a response that is not valid JSON.")


def _object_slice(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1 or end <= start:
        return None

    return text[start : end + 1]


def _validate(model: type, payload: dict[str, Any]) -> Any:
    try:
        return model.model_validate(payload)
    except ValidationError as error:
        raise GeminiResponseError(
            "Gemini returned an incomplete or invalid assessment response."
        ) from error


class GeminiService:
    """Thin wrapper around the official google-genai SDK."""

    def __init__(
        self,
        config: GeminiConfig | None = None,
        client: Any | None = None,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
    ) -> None:
        self._config = config
        self._client = client
        self._timeout_ms = timeout_ms

    @property
    def config(self) -> GeminiConfig:
        if self._config is None:
            self._config = load_config()

        return self._config

    def _get_client(self) -> Any:
        if self._client is None:
            config = self.config
            self._client = genai.Client(
                api_key=config.api_key,
                http_options=types.HttpOptions(timeout=self._timeout_ms),
            )

        return self._client

    def _generate_json(self, prompt: str) -> dict[str, Any]:
        try:
            response = self._get_client().models.generate_content(
                model=self.config.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )
        except Exception as error:
            translated = self._translate_error(error)

            if translated is not None:
                raise translated from error

            raise

        return parse_json_object(getattr(response, "text", None))

    @staticmethod
    def _translate_error(error: Exception) -> GeminiError | None:
        if isinstance(error, (TimeoutError, httpx.TimeoutException)):
            return GeminiTimeoutError("Gemini did not respond in time. Try again.")

        if isinstance(error, genai_errors.APIError):
            code = getattr(error, "code", None)
            message = str(error).lower()

            if (
                code in (401, 403)
                or "api key" in message
                or "api_key_invalid" in message
            ):
                return GeminiAuthenticationError(
                    "Gemini rejected the API key. Check GEMINI_API_KEY."
                )

            if code == 429:
                return GeminiUnavailableError(
                    "Gemini is rate limiting requests. Try again shortly."
                )

            if code == 404:
                return GeminiConfigurationError(
                    "The configured Gemini model is unavailable. "
                    "Check GEMINI_MODEL in the backend .env file."
                )

            return GeminiUnavailableError(
                f"Gemini request failed with status {code or 'unknown'}."
            )

        if isinstance(error, (ConnectionError, httpx.TransportError)):
            return GeminiUnavailableError(
                "Could not reach Gemini. Check the network and try again."
            )

        return None

    def prepare(self, idea: IdeaSnapshot) -> AssessmentAnalysis:
        prompt = f"""You are an expert idea assessor for Ideon.

{LANGUAGE_INSTRUCTION}

Analyse the idea below. Base every statement only on the information provided.
Never invent facts. Clearly distinguish facts from assumptions.

Return ONLY a JSON object with exactly these keys:
{{
  "summary": "short assessment summary",
  "key_strengths": ["..."],
  "key_weaknesses": ["..."],
  "missing_information": ["..."],
  "critical_assumptions": ["..."],
  "uncertainty_notes": ["..."],
  "clarifying_questions": ["at most 2 questions"],
  "proposed_refined_title": "a clearer title",
  "proposed_refined_description": "a clearer, more complete description"
}}

Rules:
- Do not include scores, ratings, weighted results, or classifications.
- Ask at most 2 clarifying questions. Use an empty list if none are needed.
- Keep the proposed title and description faithful to the original idea.

Idea:
Title: {idea.title}
Description: {idea.description}
"""

        return _validate(AssessmentAnalysis, self._generate_json(prompt))

    def refine(
        self,
        idea: IdeaSnapshot,
        analysis: AssessmentAnalysis,
        answers: list[dict[str, str]],
    ) -> RefinedIdea:
        analysis_json = json.dumps(analysis.model_dump(), indent=2)
        answers_json = json.dumps(answers, indent=2)

        prompt = f"""You are refining an idea for Ideon before assessment.

{LANGUAGE_INSTRUCTION}

Use the original idea, the previous analysis, and the user's clarification
answers. Do not invent facts. If an answer is blank, do not treat it as new
information. Do not include scores, ratings, or classifications.

Return ONLY a JSON object with exactly these keys:
{{
  "title": "refined title",
  "description": "refined description"
}}

Original idea:
Title: {idea.title}
Description: {idea.description}

Previous analysis:
{analysis_json}

Clarification answers:
{answers_json}
"""

        return _validate(RefinedIdea, self._generate_json(prompt))

    def score(
        self,
        idea: IdeaSnapshot,
        analysis: AssessmentNarrative,
        confirmed_title: str,
        confirmed_description: str,
    ) -> ScoringPayload:
        analysis_json = json.dumps(analysis.model_dump(), indent=2)

        prompt = f"""You are the assessment engine for Ideon.

{LANGUAGE_INSTRUCTION}

Evaluate the confirmed idea against every rubric criterion. Score each
criterion with an integer from 0 to 100, where a higher Risk Control score
means better risk management. Every criterion must appear exactly once.

Rubric (weights are applied by Python, do not calculate any weighted or final
score yourself):
{_rubric_lines()}

Criterion names to use exactly:
{_criteria_json_names()}

Base every statement only on the information provided. Never invent facts.
Clearly distinguish evidence from assumptions. If evidence is unavailable, say
so explicitly in the evidence field.

Return ONLY a JSON object with exactly these keys:
{{
  "summary": "short assessment summary",
  "key_strengths": ["..."],
  "key_weaknesses": ["..."],
  "missing_information": ["..."],
  "critical_assumptions": ["..."],
  "uncertainty_notes": ["..."],
  "criteria": [
    {{
      "criterion": "one exact criterion name",
      "score": 0,
      "reasoning": "why this score",
      "evidence": "facts from the idea that support it",
      "assumptions": "assumptions behind it"
    }}
  ]
}}

Rules:
- Return exactly {len(RUBRIC)} criteria, each exactly once.
- Scores must be integers between 0 and 100.
- Every criterion must include non-empty reasoning, evidence, and assumptions.
- Do not return a final score or classification.

Original idea:
Title: {idea.title}
Description: {idea.description}

Previous analysis:
{analysis_json}

Confirmed idea to evaluate:
Title: {confirmed_title}
Description: {confirmed_description}
"""

        payload = self._generate_json(prompt)
        narrative = _validate(AssessmentNarrative, payload)
        criteria = payload.get("criteria")

        if not isinstance(criteria, list) or not all(
            isinstance(item, dict) for item in criteria
        ):
            raise GeminiResponseError(
                "Gemini returned an invalid assessment criteria payload."
            )

        return ScoringPayload(narrative=narrative, criteria=criteria)

    def generate_improvement_proposal(
        self,
        current_title: str,
        current_description: str,
        latest_assessment: dict[str, Any],
        iteration_number: int,
    ) -> GeneratedProposalContent:
        """Generate a focused, high-impact proposal to improve the idea."""
        assessment_summary = latest_assessment.get("summary", "")
        weaknesses = json.dumps(latest_assessment.get("key_weaknesses", []), ensure_ascii=False)
        missing_info = json.dumps(latest_assessment.get("missing_information", []), ensure_ascii=False)
        criteria_summary = []
        for c in latest_assessment.get("criteria", []):
            criteria_summary.append(f"- {c.get('criterion')}: {c.get('score')}/100 (Reasoning: {c.get('reasoning')})")
        criteria_text = "\n".join(criteria_summary)

        prompt = f"""You are the expert Idea Improvement Engine for Ideon.

{LANGUAGE_INSTRUCTION}

Your task is to propose concrete, constructive improvements to the idea below, specifically addressing the weaknesses, missing information, and low-scoring criteria from its latest assessment.

Improvement Iteration: #{iteration_number}

Idea to Improve:
Title: {current_title}
Description: {current_description}

Latest Assessment Findings:
Summary: {assessment_summary}
Key Weaknesses:
{weaknesses}
Missing Information:
{missing_info}
Criteria Scores & Reasoning:
{criteria_text}

Rules:
1. Propose an improved title that is catchy, clear, and professional.
2. Propose an improved description that directly resolves identified weaknesses, clarifies missing details, strengthens feasibility and impact, while remaining faithful to the user's core vision.
3. Provide a clear rationale explaining why these improvements make the idea stronger.
4. Provide a list of key changes (short bullet points).
5. Do NOT include scores or ratings.

Return ONLY a JSON object with exactly these keys:
{{
  "proposed_title": "improved title",
  "proposed_description": "detailed improved description",
  "rationale": "explanation of how this resolves key weaknesses",
  "key_changes": [
    "first concrete change made",
    "second concrete change made"
  ]
}}
"""
        return _validate(GeneratedProposalContent, self._generate_json(prompt))
