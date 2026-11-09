import unittest

from scoring import RUBRIC, ScoringError, classify, score_assessment


def criteria_with_scores(*scores: int) -> list[dict]:
    return [
        {
            "criterion": rubric.name,
            "score": score,
            "reasoning": "Reasoning.",
            "evidence": "Evidence.",
            "assumptions": "Assumptions.",
        }
        for rubric, score in zip(RUBRIC, scores)
    ]


class RubricTests(unittest.TestCase):
    def test_rubric_matches_the_required_weights(self):
        self.assertEqual(
            [(criterion.name, criterion.weight) for criterion in RUBRIC],
            [
                ("Impact", 0.30),
                ("Feasibility", 0.25),
                ("Efficiency & Cost", 0.15),
                ("Risk Control", 0.15),
                ("Goal Alignment", 0.15),
            ],
        )
        self.assertAlmostEqual(sum(criterion.weight for criterion in RUBRIC), 1.0)

    def test_weighted_calculation(self):
        result = score_assessment(criteria_with_scores(100, 80, 60, 40, 20))

        self.assertEqual(result.final_score, 68.0)
        self.assertEqual(result.classification, "Promising")
        self.assertEqual(
            [criterion.weighted_score for criterion in result.criteria],
            [30.0, 20.0, 9.0, 6.0, 3.0],
        )

    def test_results_follow_rubric_order(self):
        payload = list(reversed(criteria_with_scores(10, 20, 30, 40, 50)))
        result = score_assessment(payload)

        self.assertEqual(
            [criterion.criterion for criterion in result.criteria],
            [criterion.name for criterion in RUBRIC],
        )


class ClassificationTests(unittest.TestCase):
    def test_boundaries(self):
        cases = [
            (100, "Strong"),
            (80, "Strong"),
            (79.99, "Promising"),
            (65, "Promising"),
            (64.99, "Needs Improvement"),
            (50, "Needs Improvement"),
            (49.99, "Weak"),
            (0, "Weak"),
        ]

        for score, expected in cases:
            with self.subTest(score=score):
                self.assertEqual(classify(score), expected)

    def test_scored_classification_uses_rounded_final_score(self):
        self.assertEqual(
            score_assessment(criteria_with_scores(80, 80, 80, 80, 80)).classification,
            "Strong",
        )
        self.assertEqual(
            score_assessment(criteria_with_scores(65, 65, 65, 65, 65)).classification,
            "Promising",
        )
        self.assertEqual(
            score_assessment(criteria_with_scores(50, 50, 50, 50, 50)).classification,
            "Needs Improvement",
        )
        self.assertEqual(
            score_assessment(criteria_with_scores(49, 49, 49, 49, 49)).classification,
            "Weak",
        )


class ValidationTests(unittest.TestCase):
    def assert_invalid(self, payload):
        with self.assertRaises(ScoringError):
            score_assessment(payload)

    def test_missing_criteria_rejected(self):
        self.assert_invalid(criteria_with_scores(50, 50, 50, 50))

    def test_duplicate_criteria_rejected(self):
        payload = criteria_with_scores(50, 50, 50, 50, 50)
        payload[4]["criterion"] = payload[0]["criterion"]
        self.assert_invalid(payload)

    def test_unknown_criterion_rejected(self):
        payload = criteria_with_scores(50, 50, 50, 50, 50)
        payload[0]["criterion"] = "Popularity"
        self.assert_invalid(payload)

    def test_out_of_range_scores_rejected(self):
        for score in (-1, 101, 1000):
            with self.subTest(score=score):
                payload = criteria_with_scores(50, 50, 50, 50, 50)
                payload[0]["score"] = score
                self.assert_invalid(payload)

    def test_non_integer_scores_rejected(self):
        for score in (80.5, "80", True, None):
            with self.subTest(score=score):
                payload = criteria_with_scores(50, 50, 50, 50, 50)
                payload[0]["score"] = score
                self.assert_invalid(payload)

    def test_missing_explanation_fields_rejected(self):
        for field in ("reasoning", "evidence", "assumptions"):
            with self.subTest(field=field):
                payload = criteria_with_scores(50, 50, 50, 50, 50)
                del payload[0][field]
                self.assert_invalid(payload)

    def test_non_mapping_criterion_rejected(self):
        payload = criteria_with_scores(50, 50, 50, 50, 50)
        payload[0] = "Impact"
        self.assert_invalid(payload)


if __name__ == "__main__":
    unittest.main()
