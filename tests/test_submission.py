import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from neorando.schemas import AgentAnswer

# ── Test du pipeline CLI run (avec agent mocké) ──────────────────────────────


class TestCLIRun:
    """Teste la commande `neorando run` avec un agent factice."""

    def test_run_produces_valid_json(self, tmp_path: Path):
        """La commande run produit un JSON valide même avec un agent trivial."""
        # Créer un mini CSV de questions
        csv_path = tmp_path / "questions.csv"
        pd.DataFrame({"Query": ["Q1", "Q2", "Q3"]}).to_csv(csv_path, index=False)

        output_json = tmp_path / "submission.json"

        # Mocker answer_question pour retourner une réponse simple
        dummy_answer = AgentAnswer(numeric=42.0)

        with patch("neorando.agent.answer_question", return_value=dummy_answer):
            from click.testing import CliRunner

            from neorando.cli import main

            runner = CliRunner()
            result = runner.invoke(main, ["run", str(csv_path), "-o", str(output_json)])

        assert result.exit_code == 0, f"CLI échouée :\n{result.output}"
        assert output_json.exists(), "Le fichier JSON n'a pas été créé"

        with open(output_json, encoding="utf-8") as f:
            submission = json.load(f)

        assert isinstance(submission, dict)
        assert "results" in submission
        assert "usage" in submission
        results = submission["results"]
        assert isinstance(results, list)
        assert len(results) == 3
        required_keys = {"query", "answer", "numeric", "boolean", "items", "time"}
        for entry in results:
            assert required_keys.issubset(entry.keys())

    def test_run_fails_without_query_column(self, tmp_path: Path):
        """Si le CSV n'a pas de colonne Query, la commande échoue."""
        csv_path = tmp_path / "bad.csv"
        pd.DataFrame({"Question": ["Q1"]}).to_csv(csv_path, index=False)

        from click.testing import CliRunner

        from neorando.cli import main

        runner = CliRunner()
        result = runner.invoke(
            main, ["run", str(csv_path), "-o", str(tmp_path / "out.json")]
        )
        assert result.exit_code != 0


# ── Test de l'interface agent ────────────────────────────────────────────────


class TestAgentInterface:
    """Vérifie que answer_question est bien définie et retourne le bon type."""

    def test_signature_exists(self):
        """La fonction answer_question existe dans neorando.agent."""
        import inspect

        from neorando.agent import answer_question

        sig = inspect.signature(answer_question)
        params = list(sig.parameters.keys())
        assert "question" in params, (
            "answer_question doit accepter un paramètre 'question'"
        )
