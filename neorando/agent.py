"""Agent de réponse aux questions sur les randonnées.

C'est dans ce module que vous devez implémenter la logique de votre agent.
La fonction `answer_question` est appelée par la CLI pour chaque question.

N'hésitez pas à créer d'autres fonctions ou classes dans ce module pour organiser votre code,
ainsi que d'autres modules si nécessaire. L'important est que `answer_question` prenne une chaîne de caractères
en entrée et retourne une instance de `AgentAnswer`.
"""

from __future__ import annotations

from neorando.schemas import AgentAnswer


def answer_question(question: str) -> AgentAnswer:
    """Répond à une question sur les randonnées autour de Grenoble.

    Args:
        question (str): La question en français à laquelle l'agent doit répondre.

    Returns:
        AgentAnswer: La réponse structurée, avec exactement UN des champs
        `answer`, `numeric`, `boolean` ou `items` renseigné.
    """
    # raise NotImplementedError("À vous de jouer ! Implémentez votre agent ici.")
    return AgentAnswer(
        answer="Ceci est une réponse d'exemple. Remplacez-la par votre propre logique !"
    )
