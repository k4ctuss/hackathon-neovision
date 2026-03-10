"""Schéma de sortie structuré pour l'agent randonnées."""

from typing import Self

from pydantic import BaseModel, Field, model_validator


class AgentAnswer(BaseModel):
    """Réponse structurée de l'agent randonnées.

    Exactement UN des quatre champs doit être renseigné selon le type de question :
    - `answer`  → réponse textuelle (nom de randonnée, commune, point de départ, …)
    - `numeric` → valeur numérique (distance, durée, nombre, dénivelé, …)
    - `boolean` → oui / non
    - `items`   → liste ordonnée de chaînes de caractères (noms de randonnées, communes, …)
    """

    answer: str | None = Field(
        default=None,
        description=(
            "Réponse textuelle : nom de randonnée, commune, point de départ, "
            "type de parcours, niveau de difficulté, URL, etc. "
            "Remplis CE champ quand la question attend UNE valeur textuelle."
        ),
    )
    numeric: float | None = Field(
        default=None,
        description=(
            "Valeur numérique : distance (km), dénivelé (m), durée (min), "
            "nombre de randonnées, temps de trajet en voiture (min), "
            "distance à vol d'oiseau (km), etc. "
            "Remplis CE champ quand la question attend UN nombre."
        ),
    )
    boolean: bool | None = Field(
        default=None,
        description=(
            "Réponse booléenne : oui (true) / non (false). "
            "Remplis CE champ quand la question attend une réponse oui/non."
        ),
    )
    items: list[str] | None = Field(
        default=None,
        description=(
            "Liste ordonnée de chaînes de caractères : noms de randonnées, "
            "communes, points de départ, etc. "
            "Remplis CE champ quand la question attend PLUSIEURS valeurs."
        ),
    )

    _FIELD_NAMES: tuple[str, ...] = ("answer", "numeric", "boolean", "items")

    @model_validator(mode="after")
    def exactly_one_field_set(self) -> Self:
        """Vérifie qu'exactement un des quatre champs est renseigné."""
        filled = [f for f in self._FIELD_NAMES if getattr(self, f) is not None]
        if len(filled) != 1:
            raise ValueError(
                f"Exactement UN champ parmi {self._FIELD_NAMES} doit être renseigné, "
                f"mais {len(filled)} trouvé(s) : {filled or 'aucun'}"
            )
        return self
