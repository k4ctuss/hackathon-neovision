"""Agent de réponse aux questions sur les randonnées.

C'est dans ce module que vous devez implémenter la logique de votre agent.
La fonction `answer_question` est appelée par la CLI pour chaque question.

N'hésitez pas à créer d'autres fonctions ou classes dans ce module pour organiser votre code,
ainsi que d'autres modules si nécessaire. L'important est que `answer_question` prenne une chaîne de caractères
en entrée et retourne une instance de `AgentAnswer`.
"""

from __future__ import annotations

import asyncio
import aiohttp
import certifi
import ssl
import json
import logging
from datetime import datetime, timedelta
from typing import Any, List

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeout,
)
from playwright.async_api import (
    async_playwright,
)
from playwright_stealth import Stealth

from neorando.schemas import AgentAnswer

load_dotenv()
SOURCE_URL = "https://www.grenoble-tourisme.com/fr/faire/randonner/a-pied/"


# ----- tools -----

# Browser-like User-Agent for actual page requests
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


@tool
async def scraper_tool(
    url: str,
    selector: str | None = None,
    include_links: bool = False,
    max_length: int = 50000,
) -> dict:
    """
    Scrape et extrait le contenu textuel d'une page web.

    Utilise un navigateur sans interface (headless) pour rendre le JavaScript et contourner la détection des robots.
    À utiliser lorsque tu dois lire le contenu d'une URL spécifique, extraire des données d'un site web, ou lire des articles/documentations.

    Args :
    url : URL de la page web à scraper
    selector : Sélecteur CSS pour cibler un contenu spécifique (ex : 'article', '.main-content')
    include_links : Inclure les liens extraits dans la réponse
    max_length : Longueur maximale du texte extrait (1000-500000)

    Returns :
    Dictionnaire avec le contenu scrappé (url, titre, description, contenu, longueur) ou un dict d'erreur
    """

    max_length = max(1000, min(max_length, 500000))

    try:
        # Validate URL
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        logger.debug(
            "[scraper] Début du scraping → %s (selector=%s, max_length=%d)",
            url,
            selector,
            max_length,
        )

        # Launch headless browser with stealth
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            try:
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent=BROWSER_USER_AGENT,
                    locale="fr-FR",
                )
                page = await context.new_page()
                await Stealth().apply_stealth_async(page)

                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=50000,
                )

                if response is None:
                    return {"error": "Navigation failed: no response received"}

                if response.status != 200:
                    return {"error": f"HTTP {response.status}: Failed to fetch URL"}

                content_type = response.headers.get("content-type", "").lower()
                if not any(
                    t in content_type for t in ["text/html", "application/xhtml+xml"]
                ):
                    return {
                        "error": (
                            f"Skipping non-HTML content (Content-Type: {content_type})"
                        ),
                        "url": url,
                        "skipped": True,
                    }

                # Wait for JS to finish rendering dynamic content
                try:
                    await page.wait_for_load_state("networkidle", timeout=3000)
                except PlaywrightTimeout:
                    pass  # Proceed with whatever has loaded

                # Get fully rendered HTML
                html_content = await page.content()
            finally:
                await browser.close()

        # Parse rendered HTML with BeautifulSoup
        soup = BeautifulSoup(html_content, "html.parser")

        # Remove noise elements
        for tag in soup(
            [
                "script",
                "style",
                "nav",
                "footer",
                "header",
                "aside",
                "noscript",
                "iframe",
            ]
        ):
            tag.decompose()

        # Get title and description
        title = soup.title.get_text(strip=True) if soup.title else ""

        description = ""
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            description = meta_desc.get("content", "")

        # Target content
        if selector:
            content_elem = soup.select_one(selector)
            if not content_elem:
                return {"error": f"No elements found matching selector: {selector}"}
            text = content_elem.get_text(separator=" ", strip=True)
        else:
            # Auto-detect main content
            main_content = (
                soup.find("article")
                or soup.find("main")
                or soup.find(attrs={"role": "main"})
                or soup.find(class_=["content", "post", "entry", "article-body"])
                or soup.find("body")
            )
            text = (
                main_content.get_text(separator=" ", strip=True) if main_content else ""
            )

        # Clean up whitespace
        text = " ".join(text.split())

        # Truncate if needed
        if len(text) > max_length:
            text = text[:max_length] + "..."

        result: dict[str, Any] = {
            "url": url,
            "title": title,
            "description": description,
            "content": text,
            "length": len(text),
        }

        # Extract links if requested
        if include_links:
            links: list[dict[str, str]] = []
            base_url = str(response.url)  # Use final URL after redirects
            for a in soup.find_all("a", href=True)[:50]:
                href = a["href"]
                # Convert relative URLs to absolute URLs
                absolute_href = urljoin(base_url, href)
                link_text = a.get_text(strip=True)
                if link_text and absolute_href:
                    links.append({"text": link_text, "href": absolute_href})
            result["links"] = links

        logger.debug(
            "[scraper] Scraping terminé → %s (%d caractères extraits)",
            url,
            result["length"],
        )
        return result

    except PlaywrightTimeout:
        logger.warning("[scraper] Timeout → %s", url)
        return {"error": "Request timed out"}
    except PlaywrightError as e:
        logger.error("[scraper] Erreur navigateur → %s", e)
        return {"error": f"Browser error: {e!s}"}
    except Exception as e:
        logger.error("[scraper] Erreur inattendue → %s", e)
        return {"error": f"Scraping failed: {e!s}"}


@tool
async def address_to_location_tool(lieu: str) -> dict:
    """Obtenir les coordonnées géographiques (latitude, longitude) d'un lieu.

    Utilise l'API Nominatim d'OpenStreetMap. Le lieu est un texte humain
    (ex : 'gare de Grenoble', 'Col de Vence, Alpes-Maritimes') qui sera
    automatiquement encodé en query string pour la requête.


    Args:
        lieu (str): Texte humain décrivant le lieu à géocoder.
                       Exemples : 'gare de Grenoble', 'Col du Galibier, Savoie'

    Returns:
        dict: Coordonnées du lieu ou dict d'erreur.
        Exemple de succès :
        {
            "display_name": "Gare de Grenoble, Grenoble, Isère, France",
            "lat": 45.1916,
            "lon": 5.7167
        }
        Exemple d'erreur :
        {"error": "Aucun résultat trouvé pour : 'xyz inexistant'"}
    """
    API_BASE_URL = "https://nominatim.openstreetmap.org/search"
    # Nominatim attend une query string encodée
    params = {
        "q": lieu,
        "format": "json",
        "limit": 1,
    }
    headers = {"User-Agent": BROWSER_USER_AGENT}
    # ssl certif pour fix un problème de SSL sur les requetes de l'api qui me refusait, j'ai pas trouver d'autre solution que ce que chat a dit.
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    logger.debug("[address_to_location_tool] Géocodage → '%s'", lieu)
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(API_BASE_URL, params=params, timeout=aiohttp.ClientTimeout(total=10), ssl=ssl_ctx) as response:
                response.raise_for_status()
                data = await response.json()
    except aiohttp.ClientError as e:
        logger.error("[address_to_location_tool] Erreur de requête → %s", e)
        return {"error": f"Request error: {e!s}"}

    if not data:
        logger.warning("[address_to_location_tool] Aucun résultat pour → '%s'", lieu)
        return {"error": f"Aucun résultat trouvé pour : '{lieu}'"}

    first = data[0]
    result = {
        "display_name": first.get("display_name", ""),
        "lat": float(first["lat"]),
        "lon": float(first["lon"]),
    }
    logger.debug("[address_to_location_tool] Résultat → %s", result)
    return result
        

TOOLS = [scraper_tool, address_to_location_tool]

# Initialisation des LLMs et de l'agent
# mini for reasoning, nano for structured output (AgentAnswer)
llm_gpt5_mini = ChatOpenAI(model="gpt-5-mini", temperature=0)
llm_gpt5_nano = ChatOpenAI(model="gpt-5-nano", temperature=0).with_structured_output(
    AgentAnswer
)

# TODO : improve system priompt with tools descritpion
SYSTEM_MESSAGE = (
    "Tu es Neorando, un agent IA expert des randonnées autour de Grenoble. "
    f"Ta mission est de répondre précisément et efficacement à toutes les questions concernant les randonnées, en utilisant des données issues du site officiel du tourisme de Grenoble. voici le lien : {SOURCE_URL} mais aussi des outils de scraping et de géocodage pour récupérer les informations nécessaires. "
    "Pour chaque question, analyse le type de réponse attendue (texte, nombre, oui/non, liste) et fournis une réponse structurée selon le schéma fourni (un seul champ renseigné). "
    "Ne demande jamais d'informations supplémentaires à l'utilisateur : récupère et traite les données toi-même. "
    "Sois concis, exact, et veille à ce que ta réponse soit toujours reproductible. "
    "Si une question fait référence à une randonnée ou une information déjà mentionnée, vérifie toujours les détails dans les données du site. "
    "N'utilise pas de sources externes autres que le site officiel. "
)

agent = create_agent(llm_gpt5_mini, tools=TOOLS, system_prompt=SYSTEM_MESSAGE, debug=True)


def answer_question(question: str, history: List[BaseMessage]) -> AgentAnswer:
    """Répond à une question sur les randonnées autour de Grenoble.

    Args:
        question (str): La question en français à laquelle l'agent doit répondre.

    Returns:
        AgentAnswer: La réponse structurée, avec exactement UN des champs
        `answer`, `numeric`, `boolean` ou `items` renseigné.
    """
    return asyncio.run(_answer_question_async(question, history))


async def _answer_question_async(
    question: str, history: List[BaseMessage]
) -> AgentAnswer:
    try:
        result = await agent.ainvoke(
            {"messages": history + [HumanMessage(content=question)]},
            config={"recursion_limit": 50},
        )
        last_message = result["messages"][-1]
        logger.debug("[agent] Réponse brute de l'agent :\n%s", last_message.content)
        history += [HumanMessage(content=question), last_message]
        # Formatage de la réponse en AgentAnswer via gpt-5-nano
        # On passe la question ET la réponse de l'agent pour que nano
        # sache quel champ remplir (answer, numeric, boolean ou items)

        formatting_prompt = HumanMessage(
            content=(
                f"Question originale : {question}\n\n"
                f"Réponse de l'agent : {last_message.content}\n\n"
                "En te basant sur la question et la réponse ci-dessus, "
                "remplis Exactement UN des quatre champs doit être renseigné selon le type de question :"
                " - `answer`  → réponse textuelle (nom de randonnée, commune, point de départ, …)"
                " - `numeric` → valeur numérique (distance, durée, nombre, dénivelé, …)"
                " - `boolean` → oui / non"
                " - `items`   → liste ordonnée de chaînes de caractères (noms de randonnées, communes, …)"
            )
        )
        return await llm_gpt5_nano.ainvoke([formatting_prompt])
    except Exception as e:
        logger.error("[agent] Erreur dans answer_question : %s", e, exc_info=True)
        history += [
            HumanMessage(content=question),
            AIMessage(content=f"Erreur : {str(e)}"),
        ]
        return AgentAnswer(
            answer=f"Erreur lors du traitement de la question : {str(e)}"
        )
