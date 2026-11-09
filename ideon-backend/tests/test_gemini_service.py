import json
import os
import unittest
from unittest.mock import patch

from google.genai import errors as genai_errors

from gemini_service import (
    LANGUAGE_INSTRUCTION,
    GeminiAuthenticationError,
    GeminiConfig,
    GeminiConfigurationError,
    GeminiResponseError,
    GeminiService,
    GeminiTimeoutError,
    GeminiUnavailableError,
    load_config,
    parse_json_object,
)
from assessment_models import IdeaSnapshot
from tests.support import ANALYSIS, CRITERIA, NARRATIVE


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)

        if isinstance(item, BaseException):
            raise item

        if isinstance(item, str):
            return FakeResponse(item)

        return FakeResponse(json.dumps(item))


class FakeClient:
    def __init__(self, responses):
        self.models = FakeModels(responses)


def service_with(*responses):
    client = FakeClient(responses)
    return (
        GeminiService(
            config=GeminiConfig(api_key="test-key", model="test-model"),
            client=client,
        ),
        client,
    )


class ConfigurationTests(unittest.TestCase):
    def test_config_loads_from_environment(self):
        with patch.dict(
            os.environ,
            {"GEMINI_API_KEY": "key-123", "GEMINI_MODEL": "gemini-test"},
            clear=True,
        ):
            config = load_config()

        self.assertEqual(config.api_key, "key-123")
        self.assertEqual(config.model, "gemini-test")

    def test_missing_api_key_is_reported(self):
        with patch.dict(os.environ, {"GEMINI_MODEL": "gemini-test"}, clear=True):
            with self.assertRaises(GeminiConfigurationError):
                load_config()

    def test_missing_model_is_reported(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "key-123"}, clear=True):
            with self.assertRaises(GeminiConfigurationError):
                load_config()

    def test_configuration_is_loaded_lazily(self):
        service = GeminiService()
        idea = IdeaSnapshot(id=1, title="Portal", description="A portal.")

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(GeminiConfigurationError):
                service.prepare(idea)


class PreparationTests(unittest.TestCase):
    def test_prepare_returns_no_scores(self):
        service, client = service_with(ANALYSIS.model_dump())

        result = service.prepare(
            IdeaSnapshot(
                id=1, title="Portal", description="A portal to Japan."
            )
        )

        self.assertEqual(result, ANALYSIS)
        self.assertNotIn("criteria", result.model_dump())
        prompt = client.models.calls[0]["contents"]
        self.assertIn("Portal", prompt)
        self.assertIn("Do not include scores", prompt)

    def test_prepare_rejects_incomplete_payload(self):
        payload = ANALYSIS.model_dump()
        del payload["summary"]
        service, _ = service_with(payload)

        with self.assertRaises(GeminiResponseError):
            service.prepare(
                IdeaSnapshot(
                    id=1, title="Portal", description="A portal."
                )
            )

    def test_markdown_fences_are_tolerated(self):
        service, _ = service_with(
            "```json\n" + json.dumps(ANALYSIS.model_dump()) + "\n```"
        )

        result = service.prepare(
            IdeaSnapshot(
                id=1, title="Portal", description="A portal."
            )
        )

        self.assertEqual(result.proposed_refined_title, "Refined portal")


class RefinementTests(unittest.TestCase):
    def test_answers_are_included_in_the_prompt(self):
        service, client = service_with(
            {"title": "Refined", "description": "Refined description."}
        )
        idea = IdeaSnapshot(
            id=1, title="Portal", description="A portal."
        )

        result = service.refine(
            idea,
            ANALYSIS,
            [{"question": "Who is the customer?", "answer": "Small studios."}],
        )

        self.assertEqual(result.title, "Refined")
        prompt = client.models.calls[0]["contents"]
        self.assertIn("Who is the customer?", prompt)
        self.assertIn("Small studios.", prompt)

    def test_refine_rejects_blank_refined_text(self):
        service, _ = service_with({"title": "  ", "description": "Text."})

        with self.assertRaises(GeminiResponseError):
            service.refine(
                IdeaSnapshot(
                    id=1, title="Portal", description="A portal."
                ),
                ANALYSIS,
                [],
            )


class ScoringPromptTests(unittest.TestCase):
    def test_score_returns_criteria_and_uses_authoritative_rubric(self):
        payload = {**NARRATIVE.model_dump(), "criteria": CRITERIA}
        service, client = service_with(payload)
        idea = IdeaSnapshot(
            id=1, title="Portal", description="A portal."
        )

        result = service.score(
            idea, NARRATIVE, "Refined portal", "A refined description."
        )

        self.assertEqual(len(result.criteria), 5)
        self.assertEqual(result.narrative, NARRATIVE)
        prompt = client.models.calls[0]["contents"]
        for criterion in ("Impact", "Feasibility", "Efficiency & Cost", "Risk Control", "Goal Alignment"):
            self.assertIn(criterion, prompt)
        self.assertIn("30%", prompt)
        self.assertIn("25%", prompt)
        self.assertIn("Refined portal", prompt)
        self.assertIn("do not calculate any weighted", prompt)

    def test_missing_criteria_field_is_rejected(self):
        service, _ = service_with(NARRATIVE.model_dump())

        with self.assertRaises(GeminiResponseError):
            service.score(
                IdeaSnapshot(
                    id=1, title="Portal", description="A portal."
                ),
                NARRATIVE,
                "Refined",
                "Description.",
            )


class LanguageInstructionTests(unittest.TestCase):
    def test_english_input_still_requires_bahasa_indonesia(self):
        service, client = service_with(
            ANALYSIS.model_dump(),
            {
                "title": "Refined English title",
                "description": "Refined English description.",
            },
            {**NARRATIVE.model_dump(), "criteria": CRITERIA},
        )
        idea = IdeaSnapshot(
            id=1,
            title="English idea",
            description="An idea written in English.",
        )

        analysis = service.prepare(idea)
        refined = service.refine(
            idea,
            ANALYSIS,
            [{"question": "Who is the user?", "answer": "Small studios."}],
        )
        payload = service.score(
            idea,
            NARRATIVE,
            "Confirmed English title",
            "Confirmed English description.",
        )

        self.assertEqual(analysis, ANALYSIS)
        self.assertEqual(refined.title, "Refined English title")
        self.assertEqual(payload.narrative, NARRATIVE)
        self.assertEqual(len(payload.criteria), 5)

        self.assertEqual(len(client.models.calls), 3)

        for call in client.models.calls:
            prompt = call["contents"]
            self.assertIn("Bahasa Indonesia", prompt)
            self.assertIn(LANGUAGE_INSTRUCTION, prompt)

        prepare_prompt, refine_prompt, score_prompt = [
            call["contents"] for call in client.models.calls
        ]
        self.assertIn('"summary"', prepare_prompt)
        self.assertIn('"title"', refine_prompt)
        self.assertIn('"criteria"', score_prompt)


class ErrorHandlingTests(unittest.TestCase):
    def test_invalid_json_is_rejected(self):
        service, _ = service_with("This is not JSON.")

        with self.assertRaises(GeminiResponseError):
            service.prepare(
                IdeaSnapshot(
                    id=1, title="Portal", description="A portal."
                )
            )

    def test_timeout_is_mapped(self):
        service, _ = service_with(TimeoutError("slow"))

        with self.assertRaises(GeminiTimeoutError):
            service.prepare(
                IdeaSnapshot(
                    id=1, title="Portal", description="A portal."
                )
            )

    def test_invalid_api_key_is_mapped(self):
        service, _ = service_with(
            genai_errors.ClientError(401, {"error": {"message": "bad key"}})
        )

        with self.assertRaises(GeminiAuthenticationError):
            service.prepare(
                IdeaSnapshot(
                    id=1, title="Portal", description="A portal."
                )
            )

    def test_invalid_api_key_400_is_mapped(self):
        service, _ = service_with(
            genai_errors.ClientError(
                400,
                {"error": {"message": "API key not valid. Please pass a valid API key."}},
            )
        )

        with self.assertRaises(GeminiAuthenticationError):
            service.prepare(
                IdeaSnapshot(
                    id=1, title="Portal", description="A portal."
                )
            )

    def test_model_not_found_is_mapped(self):
        service, _ = service_with(
            genai_errors.ClientError(
                404,
                {
                    "error": {
                        "message": "This model is no longer available to new users."
                    }
                },
            )
        )

        with self.assertRaises(GeminiConfigurationError) as context:
            service.prepare(
                IdeaSnapshot(
                    id=1, title="Portal", description="A portal."
                )
            )

        self.assertIn("GEMINI_MODEL", str(context.exception))

    def test_server_error_is_mapped(self):
        service, _ = service_with(
            genai_errors.ServerError(503, {"error": {"message": "unavailable"}})
        )

        with self.assertRaises(GeminiUnavailableError):
            service.prepare(
                IdeaSnapshot(
                    id=1, title="Portal", description="A portal."
                )
            )

    def test_empty_response_is_rejected(self):
        with self.assertRaises(GeminiResponseError):
            parse_json_object("")

    def test_non_object_json_is_rejected(self):
        with self.assertRaises(GeminiResponseError):
            parse_json_object("[1, 2, 3]")


if __name__ == "__main__":
    unittest.main()
