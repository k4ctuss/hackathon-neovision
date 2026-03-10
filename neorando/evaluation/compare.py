"""Fonctions de comparaison utilisées par le pipeline d'évaluation.

Chaque fonction renvoie un score entre 0.0 et 1.0.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from rapidfuzz import fuzz
from unidecode import unidecode

# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    """Met en minuscules, supprime les accents, normalise les espaces et la ponctuation."""
    text = unidecode(text).lower().strip()
    text = re.sub(r"[\'\'\"\«\»\"\"\(\)\[\]\{\}\<\>]", "", text)
    text = re.sub(r"[-–—/,;:!?.]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Comparaison textuelle
# ---------------------------------------------------------------------------


def compare_text(
    actual: str | None,
    expected: str,
    *,
    method: Literal["exact", "fuzzy", "contains"] = "fuzzy",
    threshold: float = 80.0,
) -> float:
    """Compare deux valeurs textuelles.

    Args:
        actual (str | None): Réponse de l'agent.
        expected (str): Réponse attendue.
        method (Literal["exact", "fuzzy", "contains"]): Mode de comparaison.
            ``"exact"`` — correspondance exacte après normalisation → 1.0 ou 0.0.
            ``"fuzzy"`` — ratio flou (rapidfuzz) ; renvoie ratio/100 si ≥ *threshold*, sinon 0.
            ``"contains"`` — 1.0 si le texte attendu normalisé est contenu dans la
            réponse normalisée, sinon 0.
        threshold (float): Ratio flou minimal (0–100) pour considérer une correspondance.

    Returns:
        float: Score entre 0 et 1.
    """
    if actual is None:
        return 0.0

    a = _normalize(str(actual))
    e = _normalize(str(expected))

    if not e:
        return 1.0 if not a else 0.0

    if method == "exact":
        return 1.0 if a == e else 0.0
    elif method == "contains":
        return 1.0 if e in a else 0.0
    else:  # fuzzy
        # token_set_ratio est tolérant aux mots supplémentaires
        ratio = max(fuzz.token_sort_ratio(a, e), fuzz.token_set_ratio(a, e))
        return ratio / 100.0 if ratio >= threshold else 0.0


# ---------------------------------------------------------------------------
# Comparaison numérique
# ---------------------------------------------------------------------------


def compare_numeric(
    actual: float | None,
    expected: float,
    *,
    tolerance: float = 0.05,
) -> float:
    """Compare deux valeurs numériques avec une tolérance relative.

    Score = 1.0 si ``|actual - expected| / max(|expected|, 1) <= tolerance``.

    Args:
        actual (float | None): Réponse de l'agent.
        expected (float): Valeur attendue.
        tolerance (float): Tolérance relative. 0 → correspondance exacte. 0.05 → 5 %.

    Returns:
        float: Score de 1.0 ou 0.0.
    """
    if actual is None:
        return 0.0
    if expected == 0:
        return 1.0 if actual == 0 else 0.0

    rel_error = abs(actual - expected) / max(abs(expected), 1.0)
    return 1.0 if rel_error <= tolerance else 0.0


# ---------------------------------------------------------------------------
# Comparaison booléenne
# ---------------------------------------------------------------------------


def compare_boolean(actual: bool | None, expected: bool) -> float:
    """Correspondance booléenne exacte → 1.0 ou 0.0."""
    if actual is None:
        return 0.0
    return 1.0 if bool(actual) == bool(expected) else 0.0


# ---------------------------------------------------------------------------
# Comparaison de listes (items)
# ---------------------------------------------------------------------------


def compare_items(
    actual: list[str] | str | None,
    expected: list[str],
    *,
    ordered: bool = False,
    fuzzy_threshold: float = 80.0,
) -> float:
    """Compare deux listes de chaînes via un F1-score flou.

    Pour chaque élément attendu, le meilleur élément correspondant dans la
    réponse est trouvé par correspondance floue. Un match est compté si le
    ratio ≥ *fuzzy_threshold*.

    Si *ordered* est True, une pénalité d'ordre est appliquée (Kendall-tau).

    Args:
        actual (list[str] | str | None): Réponse de l'agent (liste ou chaîne JSON).
        expected (list[str]): Liste attendue.
        ordered (bool): Si True, applique une pénalité d'ordre.
        fuzzy_threshold (float): Ratio flou minimal (0–100) pour compter un match.

    Returns:
        float: F1-score entre 0 et 1.
    """
    if actual is None:
        return 0.0

    # Gestion d'une chaîne JSON en entrée
    if isinstance(actual, str):
        try:
            actual = json.loads(actual)
        except (json.JSONDecodeError, TypeError):
            actual = [actual]

    if not expected:
        return 1.0 if not actual else 0.0
    if not actual:
        return 0.0

    norm_actual = [_normalize(str(x)) for x in actual]
    norm_expected = [_normalize(str(x)) for x in expected]

    # Correspondance gloutonne : pour chaque attendu, trouver le meilleur non-utilisé
    matched_actual: set[int] = set()
    true_positives = 0

    for exp in norm_expected:
        best_score = 0.0
        best_idx = -1
        for j, act in enumerate(norm_actual):
            if j in matched_actual:
                continue
            score = fuzz.token_sort_ratio(exp, act)
            if score > best_score:
                best_score = score
                best_idx = j
        if best_score >= fuzzy_threshold and best_idx >= 0:
            matched_actual.add(best_idx)
            true_positives += 1

    precision = true_positives / len(actual) if actual else 0.0
    recall = true_positives / len(expected) if expected else 0.0

    if precision + recall == 0:
        return 0.0
    f1 = 2 * precision * recall / (precision + recall)
    return f1


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def compare(
    actual: Any,
    expected: Any,
    *,
    answer_type: str,
    comparison: str = "fuzzy",
    tolerance: float = 0.05,
    ordered: bool = False,
) -> float:
    """Dirige la comparaison vers la bonne fonction selon ``answer_type``.

    Args:
        actual (Any): Réponse de l'agent.
        expected (Any): Valeur attendue.
        answer_type (str): ``"text"``, ``"numeric"``, ``"boolean"`` ou ``"items"``.
        comparison (str): Pour le texte : ``"exact"``, ``"fuzzy"``, ``"contains"``.
        tolerance (float): Pour les comparaisons numériques.
        ordered (bool): Pour les comparaisons de listes.

    Returns:
        float: Score entre 0 et 1.

    Raises:
        ValueError: Si ``answer_type`` est inconnu.
    """
    if answer_type == "text":
        return compare_text(actual, expected, method=comparison)
    elif answer_type == "numeric":
        return compare_numeric(actual, expected, tolerance=tolerance)
    elif answer_type == "boolean":
        return compare_boolean(actual, expected)
    elif answer_type == "items":
        return compare_items(actual, expected, ordered=ordered)
    else:
        raise ValueError(f"answer_type inconnu : {answer_type!r}")
