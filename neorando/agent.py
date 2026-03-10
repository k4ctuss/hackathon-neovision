"""Agent de réponse aux questions sur les randonnées.

C'est dans ce module que vous devez implémenter la logique de votre agent.
La fonction `answer_question` est appelée par la CLI pour chaque question.

N'hésitez pas à créer d'autres fonctions ou classes dans ce module pour organiser votre code,
ainsi que d'autres modules si nécessaire. L'important est que `answer_question` prenne une chaîne de caractères
en entrée et retourne une instance de `AgentAnswer`.
"""

from __future__ import annotations

from neorando.schemas import AgentAnswer
from typing import List
import json
from datetime import datetime, timedelta
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_core.tools import tool
from langchain.agents import create_agent

from dotenv import load_dotenv
load_dotenv()

SOURCE_URL = "https://www.grenoble-tourisme.com/fr/faire/randonner/a-pied/"


TOOLS = []

llm = ChatOpenAI(model="gpt-5-mini", temperature=0)
# TODO : improve system priompt with tools descritpion
SYSTEM_MESSAGE = (
    "Tu es Neorando, un agent IA expert des randonnées autour de Grenoble. "
    "Ta mission est de répondre précisément et efficacement à toutes les questions concernant les randonnées, en utilisant uniquement des données issues du site officiel du tourisme de Grenoble. "
    "Pour chaque question, analyse le type de réponse attendue (texte, nombre, oui/non, liste) et fournis une réponse structurée selon le schéma fourni (un seul champ renseigné). "
    "Ne demande jamais d’informations supplémentaires à l’utilisateur : récupère et traite les données toi-même. "
    "Sois concis, exact, et veille à ce que ta réponse soit toujours reproductible. "
    "Si une question fait référence à une randonnée ou une information déjà mentionnée, vérifie toujours les détails dans les données du site. "
    "N’utilise pas de sources externes autres que le site officiel. "
)

agent = create_agent(llm, tools=TOOLS, prompt=SYSTEM_MESSAGE)

def answer_question(question: str, history: List[BaseMessage]) -> AgentAnswer:
    """Répond à une question sur les randonnées autour de Grenoble.

    Args:
        question (str): La question en français à laquelle l'agent doit répondre.

    Returns:
        AgentAnswer: La réponse structurée, avec exactement UN des champs
        `answer`, `numeric`, `boolean` ou `items` renseigné.
    """
    # raise NotImplementedError("À vous de jouer ! Implémentez votre agent ici.")
    try:
        result = agent.invoke(
            {"messages": history + [HumanMessage(content=question)]},
            config={"recursion_limit": 50}
        )
        history += [HumanMessage(content=question), result]
        # Return the last AI message
        #return result["messages"][-1]
        # TODO : faire la logique de reponse
        return AgentAnswer()
    except Exception as e:
        # Return error as an AI message so the conversation can continue
        #return AIMessage(content=f"Error: {str(e)}\n\nPlease try rephrasing your request or provide more specific details.")
        return AgentAnswer()
    