import json

import pytest

from neorando.evaluation.compare import (
    compare_boolean,
    compare_items,
    compare_numeric,
    compare_text,
)
from neorando.evaluation.eval import eval_submission

# ── Tests d'évaluation — comprendre comment vos réponses sont scorées ────────


class TestCompareText:
    """Montre comment l'évaluation compare les réponses textuelles."""

    def test_case_and_accents_insensitive(self):
        """La casse et les accents n'ont pas d'importance."""
        assert compare_text("Boucle de Chamechaude", "boucle de chamechaude") == 1.0
        assert compare_text("Le belvédère de Vizille", "le belvedere de vizille") == 1.0
        assert (
            compare_text(
                "Le Rachais depuis le Col de Vence", "le rachais depuis le col de vence"
            )
            == 1.0
        )

    def test_fuzzy_tolerates_small_differences(self):
        """Le mode fuzzy tolère de petites différences (mots en plus, typos)."""
        score = compare_text("Boucle de Chamechaude", "Boucle Chamechaude")
        assert score > 0.8

    def test_wrong_answer_scores_zero(self):
        """Une réponse fausse donne un score de 0."""
        assert compare_text("Grenoble", "Boucle de Chamechaude") == 0.0

    def test_none_scores_zero(self):
        """Ne pas répondre donne un score de 0."""
        assert compare_text(None, "Boucle de Chamechaude") == 0.0

    def test_exact_mode(self):
        """En mode exact, la réponse doit correspondre exactement (après normalisation)."""
        assert compare_text("Claix", "claix", method="exact") == 1.0
        assert compare_text("Claix 38", "Claix", method="exact") == 0.0


class TestCompareNumeric:
    """Montre comment l'évaluation compare les réponses numériques."""

    def test_exact_value(self):
        assert compare_numeric(42.0, 42.0) == 1.0

    def test_within_5_percent_tolerance(self):
        """Une erreur ≤ 5% est acceptée par défaut."""
        assert compare_numeric(41.0, 42.0, tolerance=0.05) == 1.0  # ~2.4% d'erreur
        assert compare_numeric(44.0, 42.0, tolerance=0.05) == 1.0  # ~4.8% d'erreur

    def test_beyond_tolerance_scores_zero(self):
        """Au-delà de la tolérance → 0."""
        assert compare_numeric(50.0, 42.0, tolerance=0.05) == 0.0

    def test_none_scores_zero(self):
        assert compare_numeric(None, 42.0) == 0.0


class TestCompareBoolean:
    """Correspondance booléenne exacte."""

    def test_correct(self):
        assert compare_boolean(True, True) == 1.0
        assert compare_boolean(False, False) == 1.0

    def test_wrong(self):
        assert compare_boolean(True, False) == 0.0
        assert compare_boolean(False, True) == 0.0

    def test_none_scores_zero(self):
        assert compare_boolean(None, True) == 0.0


class TestCompareItems:
    """Montre comment l'évaluation compare les listes (F1-score flou)."""

    def test_perfect_match(self):
        """Même éléments → score parfait."""
        assert compare_items(["A", "B", "C"], ["A", "B", "C"]) == 1.0

    def test_order_does_not_matter_by_default(self):
        """L'ordre n'impacte pas le score par défaut."""
        assert compare_items(["C", "A", "B"], ["A", "B", "C"]) == 1.0

    def test_missing_element_lowers_recall(self):
        """Un élément manquant fait baisser le score (rappel)."""
        score = compare_items(["A", "B"], ["A", "B", "C"])
        assert 0.5 < score < 1.0

    def test_extra_element_lowers_precision(self):
        """Un élément en trop fait baisser le score (précision)."""
        score = compare_items(["A", "B", "C", "D"], ["A", "B", "C"])
        assert 0.5 < score < 1.0

    def test_none_scores_zero(self):
        assert compare_items(None, ["A", "B"]) == 0.0


# ── Tests du pipeline eval_submission ────────────────────────────────────────


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


class TestEvalSubmission:
    """Vérifie que eval_submission score correctement une soumission."""

    def test_perfect_submission(self, tmp_path):
        """Une soumission parfaite obtient 100/100."""
        expected = [
            {
                "index": 0,
                "answer_type": "text",
                "expected": "Boucle de Chamechaude",
                "comparison": "fuzzy",
            },
            {
                "index": 1,
                "answer_type": "numeric",
                "expected": 6.0,
                "comparison": "exact",
                "tolerance": 0,
            },
            {
                "index": 2,
                "answer_type": "boolean",
                "expected": True,
                "comparison": "exact",
            },
        ]
        submission = [
            {
                "query": "Q0",
                "answer": "Boucle de Chamechaude",
                "numeric": None,
                "boolean": None,
                "items": None,
                "time": 1.0,
            },
            {
                "query": "Q1",
                "answer": None,
                "numeric": 6.0,
                "boolean": None,
                "items": None,
                "time": 1.0,
            },
            {
                "query": "Q2",
                "answer": None,
                "numeric": None,
                "boolean": True,
                "items": None,
                "time": 1.0,
            },
        ]
        _write_json(tmp_path / "sub.json", submission)
        _write_json(tmp_path / "exp.json", expected)

        result = eval_submission(tmp_path / "sub.json", tmp_path / "exp.json")
        assert result["mean_score"] == 100.0
        assert result["num_queries"] == 3

    def test_all_wrong_submission(self, tmp_path):
        """Une soumission entièrement fausse obtient 0/100."""
        expected = [
            {
                "index": 0,
                "answer_type": "text",
                "expected": "Boucle de Chamechaude",
                "comparison": "exact",
            },
            {
                "index": 1,
                "answer_type": "numeric",
                "expected": 83,
                "comparison": "exact",
                "tolerance": 0,
            },
        ]
        submission = [
            {
                "query": "Q0",
                "answer": "Grenoble",
                "numeric": None,
                "boolean": None,
                "items": None,
                "time": 1.0,
            },
            {
                "query": "Q1",
                "answer": None,
                "numeric": 999.0,
                "boolean": None,
                "items": None,
                "time": 1.0,
            },
        ]
        _write_json(tmp_path / "sub.json", submission)
        _write_json(tmp_path / "exp.json", expected)

        result = eval_submission(tmp_path / "sub.json", tmp_path / "exp.json")
        assert result["mean_score"] == 0.0

    def test_none_answers_score_zero(self, tmp_path):
        """Des réponses None donnent un score de 0."""
        expected = [
            {
                "index": 0,
                "answer_type": "text",
                "expected": "Claix",
                "comparison": "exact",
            },
        ]
        submission = [
            {
                "query": "Q0",
                "answer": None,
                "numeric": None,
                "boolean": None,
                "items": None,
                "time": 1.0,
            },
        ]
        _write_json(tmp_path / "sub.json", submission)
        _write_json(tmp_path / "exp.json", expected)

        result = eval_submission(tmp_path / "sub.json", tmp_path / "exp.json")
        assert result["scores"][0]["score"] == 0.0

    def test_supports_dict_format_with_results_key(self, tmp_path):
        """eval_submission accepte le format {results: [...], usage: {...}}."""
        expected = [
            {
                "index": 0,
                "answer_type": "numeric",
                "expected": 10.0,
                "comparison": "exact",
                "tolerance": 0.05,
            },
        ]
        submission = {
            "results": [
                {
                    "query": "Q0",
                    "answer": None,
                    "numeric": 10.0,
                    "boolean": None,
                    "items": None,
                    "time": 1.0,
                },
            ],
            "usage": {},
        }
        _write_json(tmp_path / "sub.json", submission)
        _write_json(tmp_path / "exp.json", expected)

        result = eval_submission(tmp_path / "sub.json", tmp_path / "exp.json")
        assert result["mean_score"] == 100.0

    def test_mismatched_length_raises(self, tmp_path):
        """Si le nombre de réponses ne correspond pas, une erreur est levée."""
        expected = [
            {
                "index": 0,
                "answer_type": "text",
                "expected": "Grenoble",
                "comparison": "exact",
            },
            {
                "index": 1,
                "answer_type": "text",
                "expected": "Claix",
                "comparison": "exact",
            },
        ]
        submission = [
            {
                "query": "Q0",
                "answer": "Grenoble",
                "numeric": None,
                "boolean": None,
                "items": None,
                "time": 1.0,
            },
        ]
        _write_json(tmp_path / "sub.json", submission)
        _write_json(tmp_path / "exp.json", expected)

        with pytest.raises(ValueError, match="nombre d'entrées"):
            eval_submission(tmp_path / "sub.json", tmp_path / "exp.json")
