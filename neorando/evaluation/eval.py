"""Pipeline d'évaluation — score une soumission JSON contre les réponses attendues."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from neorando.evaluation.compare import compare

# Chemins par défaut relatifs à la racine du projet
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_EXPECTED = _PROJECT_ROOT / "data" / "expected_answers.json"

# Correspondance answer_type → clé dans le JSON de soumission
FIELD_KEY: dict[str, str] = {
    "text": "answer",
    "numeric": "numeric",
    "boolean": "boolean",
    "items": "items",
}


def _load_json(path: Path) -> list[dict[str, Any]]:
    """Charge un fichier JSON et renvoie la liste d'objets."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _check_submission(data: list[dict[str, Any]]) -> None:
    """Vérifie que la soumission est bien formée."""
    if not isinstance(data, list):
        raise ValueError("La soumission doit être une liste JSON d'objets.")
    if len(data) > 0 and "query" not in data[0]:
        raise ValueError(
            f"Chaque objet de la soumission doit contenir une clé 'query'. "
            f"Clés trouvées : {set(data[0].keys())}"
        )


def eval_submission(
    submission_path: str | Path,
    expected_path: str | Path = DEFAULT_EXPECTED,
) -> dict[str, Any]:
    """Évalue une soumission JSON contre les réponses attendues.

    Args:
        submission_path (str | Path): Chemin vers le JSON de soumission
            (produit par ``neorando run``).
        expected_path (str | Path): Chemin vers le JSON des réponses attendues.

    Returns:
        dict[str, Any]: Dictionnaire avec les clés :
            - ``num_queries`` (int) : nombre de questions évaluées.
            - ``mean_score`` (float) : score moyen entre 0 et 100.
            - ``scores`` (list[dict]) : liste de dicts par question
              (index, query, score…).

    Raises:
        ValueError: Si la soumission est mal formée ou si le nombre d'entrées
            ne correspond pas.
    """
    submission_path = Path(submission_path)
    expected_path = Path(expected_path)

    submission = _load_json(submission_path)

    # Support both formats: flat list or {results: [...], usage: {...}}
    if isinstance(submission, dict) and "results" in submission:
        submission = submission["results"]

    _check_submission(submission)

    expected = _load_json(expected_path)

    if len(submission) != len(expected):
        raise ValueError(
            f"Le nombre d'entrées de la soumission ({len(submission)}) ne correspond "
            f"pas au nombre de questions attendues ({len(expected)})."
        )

    scores: list[dict[str, Any]] = []

    for i, exp in enumerate(expected):
        idx: int = exp.get("index", i)
        answer_type: str = exp["answer_type"]
        expected_val = exp["expected"]
        comparison: str = exp.get("comparison", "fuzzy")
        tolerance: float = exp.get("tolerance") or 0.05
        ordered: bool = exp.get("ordered", False)
        field: str = FIELD_KEY.get(answer_type, "answer")

        # Récupérer la réponse de l'élève
        row = submission[idx]
        actual = row.get(field)

        # Conversion de type si nécessaire
        if actual is None:
            pass
        elif answer_type == "numeric":
            try:
                actual = float(actual)
            except (ValueError, TypeError):
                actual = None
        elif answer_type == "boolean":
            if isinstance(actual, str):
                actual = actual.strip().lower() in ("true", "1", "yes", "oui")
            else:
                actual = bool(actual)
        elif answer_type == "items":
            if isinstance(actual, str):
                # Fallback : chaîne séparée par des pipes
                actual = [s.strip() for s in actual.split("|") if s.strip()]
            elif not isinstance(actual, list):
                actual = None

        score = compare(
            actual,
            expected_val,
            answer_type=answer_type,
            comparison=comparison,
            tolerance=tolerance,
            ordered=ordered,
        )

        scores.append(
            {
                "index": idx,
                "query": row.get("query", ""),
                "answer_type": answer_type,
                "actual": actual,
                "expected": expected_val,
                "score": round(score, 4),
            }
        )

    # Agrégation
    all_scores = [s["score"] for s in scores]
    mean_score = (
        round(sum(all_scores) / len(all_scores) * 100, 2) if all_scores else 0.0
    )

    return {
        "num_queries": len(scores),
        "mean_score": mean_score,
        "scores": scores,
    }


def print_results(results: dict[str, Any]) -> None:
    """Affiche les résultats de l'évaluation de manière lisible.

    Args:
        results (dict[str, Any]): Dictionnaire renvoyé par ``eval_submission``.
    """
    print(f"\n{'=' * 60}")
    print(
        f"  SCORE GLOBAL : {results['mean_score']:.1f} / 100  ({results['num_queries']} questions)"
    )
    print(f"{'=' * 60}")

    # Questions réussies / échouées
    passed = [s for s in results["scores"] if s["score"] >= 0.5]
    failed = [s for s in results["scores"] if s["score"] < 0.5]
    print(f"\n  ✅ Réussies : {len(passed)}   ❌ Échouées : {len(failed)}")

    if failed:
        print(f"\n❌ Questions échouées ({len(failed)}) :")
        for s in failed:
            print(f"  [{s['index']:2d}] score={s['score']:.2f}  {s['query'][:70]}")
            print(f"       attendu : {s['expected']}")
            print(f"       obtenu  : {s['actual']}")

    print()
