"""Agent de réponse aux questions sur les randonnées.

C'est dans ce module que vous devez implémenter la logique de votre agent.
La fonction `answer_question` est appelée par la CLI pour chaque question.

N'hésitez pas à créer d'autres fonctions ou classes dans ce module pour organiser votre code,
ainsi que d'autres modules si nécessaire. L'important est que `answer_question` prenne une chaîne de caractères
en entrée et retourne une instance de `AgentAnswer`.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import ssl
from pathlib import Path
from typing import Any, List
from urllib.parse import urljoin

import aiohttp
import certifi
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

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

load_dotenv()
SOURCE_URL = "https://www.grenoble-tourisme.com/fr/faire/randonner/a-pied/"

# ---------------------------------------------------------------------------
# Load cached hike data (pre-scraped)
# ---------------------------------------------------------------------------

CACHE_PATH = Path(__file__).parent.parent / "data" / "hikes.json"
_HIKES_DATA: list[dict] = []


def _load_cached_hikes() -> list[dict]:
    """Load pre-scraped hike data from cache file."""
    global _HIKES_DATA
    if _HIKES_DATA:
        return _HIKES_DATA
    if CACHE_PATH.exists():
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            _HIKES_DATA = json.load(f)
        logger.info("Loaded %d hikes from cache", len(_HIKES_DATA))
    else:
        logger.warning("No hike cache found at %s. Run 'uv run neorando scrape' first.", CACHE_PATH)
    return _HIKES_DATA


def _build_hikes_summary() -> str:
    """Build a compact summary of all hikes for the system prompt."""
    hikes = _load_cached_hikes()
    if not hikes:
        return "AUCUNE DONNÉE DE RANDONNÉE DISPONIBLE. Utilise le scraper_tool pour récupérer les données du site."

    lines = [f"BASE DE DONNÉES DES RANDONNÉES ({len(hikes)} randonnées au total) :"]
    lines.append("Format: #ID | Nom | Commune | Départ | Distance(km) | Durée(min) | D+(m) | D-(m) | Difficulté | Type | Animaux | Lat,Lon | URL")
    lines.append("-" * 40)

    for i, h in enumerate(hikes):
        lat = h.get("latitude") or ""
        lon = h.get("longitude") or ""
        coords = f"{lat},{lon}" if lat and lon else "?"
        animaux = "oui" if h.get("animaux_acceptes") is True else ("non" if h.get("animaux_acceptes") is False else "?")
        line = (
            f"#{i} | {h.get('name', '?')} | {h.get('commune', '?')} | "
            f"{h.get('depart', '?')} | {h.get('distance_km', '?')} | "
            f"{h.get('duree_min', '?')} | {h.get('denivele_positif_m', '?')} | "
            f"{h.get('denivele_negatif_m', '?')} | {h.get('difficulte', '?')} | "
            f"{h.get('type_parcours', '?')} | {animaux} | {coords} | {h.get('url', '')}"
        )
        lines.append(line)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

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
    À utiliser UNIQUEMENT si l'information n'est pas dans la base de données locale.

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
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        logger.debug("[scraper] Début du scraping → %s (selector=%s)", url, selector)

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
                    url, wait_until="domcontentloaded", timeout=50000
                )

                if response is None:
                    return {"error": "Navigation failed: no response received"}
                if response.status != 200:
                    return {"error": f"HTTP {response.status}: Failed to fetch URL"}

                content_type = response.headers.get("content-type", "").lower()
                if not any(t in content_type for t in ["text/html", "application/xhtml+xml"]):
                    return {"error": f"Skipping non-HTML content (Content-Type: {content_type})", "url": url, "skipped": True}

                try:
                    await page.wait_for_load_state("networkidle", timeout=3000)
                except PlaywrightTimeout:
                    pass

                html_content = await page.content()
            finally:
                await browser.close()

        soup = BeautifulSoup(html_content, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe"]):
            tag.decompose()

        title = soup.title.get_text(strip=True) if soup.title else ""
        description = ""
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            description = meta_desc.get("content", "")

        if selector:
            content_elem = soup.select_one(selector)
            if not content_elem:
                return {"error": f"No elements found matching selector: {selector}"}
            text = content_elem.get_text(separator=" ", strip=True)
        else:
            main_content = (
                soup.find("article") or soup.find("main")
                or soup.find(attrs={"role": "main"})
                or soup.find(class_=["content", "post", "entry", "article-body"])
                or soup.find("body")
            )
            text = main_content.get_text(separator=" ", strip=True) if main_content else ""

        text = " ".join(text.split())
        if len(text) > max_length:
            text = text[:max_length] + "..."

        result: dict[str, Any] = {
            "url": url, "title": title, "description": description,
            "content": text, "length": len(text),
        }

        if include_links:
            links: list[dict[str, str]] = []
            base_url = str(response.url)
            for a in soup.find_all("a", href=True)[:50]:
                href = a["href"]
                absolute_href = urljoin(base_url, href)
                link_text = a.get_text(strip=True)
                if link_text and absolute_href:
                    links.append({"text": link_text, "href": absolute_href})
            result["links"] = links

        logger.debug("[scraper] Scraping terminé → %s (%d chars)", url, result["length"])
        return result

    except PlaywrightTimeout:
        return {"error": "Request timed out"}
    except PlaywrightError as e:
        return {"error": f"Browser error: {e!s}"}
    except Exception as e:
        return {"error": f"Scraping failed: {e!s}"}


@tool
def query_hikes_database(
    filtre_nom: str | None = None,
    filtre_commune: str | None = None,
    filtre_difficulte: str | None = None,
    filtre_type: str | None = None,
    filtre_animaux: bool | None = None,
    tri_par: str | None = None,
    tri_descendant: bool = True,
    limite: int = 10,
) -> dict:
    """Recherche et filtre les randonnées dans la base de données locale pré-scrapée.

    Utilise cette fonction pour trouver des randonnées selon divers critères, faire des agrégations,
    des classements, etc. C'est TOUJOURS le premier outil à utiliser avant de scraper le web.

    Args:
        filtre_nom: Filtre par nom de randonnée (recherche partielle, insensible à la casse)
        filtre_commune: Filtre par commune (recherche partielle, insensible à la casse)
        filtre_difficulte: Filtre par difficulté exacte ("Facile", "Modéré", "Difficile", "Très difficile")
        filtre_type: Filtre par type de parcours ("Boucle", "Aller-retour", "Itinérance")
        filtre_animaux: Filtre par acceptation des animaux (true = acceptés, false = refusés)
        tri_par: Champ de tri ("distance_km", "duree_min", "denivele_positif_m", "denivele_negatif_m", "nom")
        tri_descendant: Tri descendant (true) ou ascendant (false). Par défaut descendant.
        limite: Nombre max de résultats à retourner (défaut 10, max 100)

    Returns:
        dict avec "total_matches" (nombre total avant limite), "results" (liste des randonnées matchées)
    """
    hikes = _load_cached_hikes()
    if not hikes:
        return {"error": "Base de données vide. Lancer 'uv run neorando scrape' d'abord."}

    results = list(hikes)

    # Apply filters
    if filtre_nom:
        fn = filtre_nom.lower()
        results = [h for h in results if fn in (h.get("name") or "").lower()]

    if filtre_commune:
        fc = filtre_commune.lower()
        results = [h for h in results if fc in (h.get("commune") or "").lower()]

    if filtre_difficulte:
        fd = filtre_difficulte.lower()
        results = [h for h in results if fd in (h.get("difficulte") or "").lower()]

    if filtre_type:
        ft = filtre_type.lower()
        results = [h for h in results if ft in (h.get("type_parcours") or "").lower()]

    if filtre_animaux is not None:
        results = [h for h in results if h.get("animaux_acceptes") == filtre_animaux]

    total = len(results)

    # Sort
    if tri_par:
        key_map = {
            "distance_km": "distance_km",
            "duree_min": "duree_min",
            "denivele_positif_m": "denivele_positif_m",
            "denivele_negatif_m": "denivele_negatif_m",
            "nom": "name",
        }
        key = key_map.get(tri_par, tri_par)
        results.sort(
            key=lambda h: h.get(key) or 0,
            reverse=tri_descendant,
        )

    # Limit
    limite = min(max(1, limite), 100)
    results = results[:limite]

    return {"total_matches": total, "results": results}


@tool
async def address_to_location_tool(lieu: str) -> dict:
    """Obtenir les coordonnées géographiques (latitude, longitude) d'un lieu.

    Utilise l'API Nominatim d'OpenStreetMap. Le lieu est un texte humain
    (ex : 'gare de Grenoble', 'Place Victor Hugo, Grenoble').

    Args:
        lieu (str): Texte humain décrivant le lieu à géocoder.

    Returns:
        dict: Coordonnées du lieu {"display_name": ..., "lat": ..., "lon": ...} ou dict d'erreur.
    """
    API_BASE_URL = "https://nominatim.openstreetmap.org/search"
    params = {"q": lieu, "format": "json", "limit": 1, "countrycodes": "fr"}
    headers = {"User-Agent": "NeoRando-Hackathon/1.0"}
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    logger.debug("[geocode] Géocodage → '%s'", lieu)
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                API_BASE_URL, params=params,
                timeout=aiohttp.ClientTimeout(total=10), ssl=ssl_ctx,
            ) as response:
                response.raise_for_status()
                data = await response.json()
    except aiohttp.ClientError as e:
        return {"error": f"Request error: {e!s}"}

    if not data:
        return {"error": f"Aucun résultat trouvé pour : '{lieu}'"}

    first = data[0]
    return {
        "display_name": first.get("display_name", ""),
        "lat": float(first["lat"]),
        "lon": float(first["lon"]),
    }


@tool
def calcul_distance_vol_oiseau(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> dict:
    """Calcule la distance à vol d'oiseau (en km) entre deux points GPS (formule de Haversine).

    Args:
        lat1: Latitude du point 1 (degrés décimaux)
        lon1: Longitude du point 1 (degrés décimaux)
        lat2: Latitude du point 2 (degrés décimaux)
        lon2: Longitude du point 2 (degrés décimaux)

    Returns:
        dict: {"distance_km": float}
    """
    try:
        R = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        distance_km = 2 * R * math.asin(math.sqrt(a))
        logger.debug("[haversine] %.7f,%.7f → %.7f,%.7f = %.3f km", lat1, lon1, lat2, lon2, distance_km)
        return {"distance_km": round(distance_km, 3)}
    except Exception as e:
        return {"error": f"Coordonnées invalides : {e!s}"}


@tool
async def calculer_itineraire_routier(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> dict:
    """Calcule l'itinéraire routier (distance et durée en voiture) entre deux points GPS.

    Utilise le service IGN/OSRM (gratuit, open source). Les coordonnées en degrés décimaux.

    Args:
        lat1: Latitude du point de départ
        lon1: Longitude du point de départ
        lat2: Latitude du point d'arrivée
        lon2: Longitude du point d'arrivée

    Returns:
        dict: {"distance_km": float, "duree_minutes": float} ou dict d'erreur
    """
    API_URL = "https://data.geopf.fr/navigation/itineraire"
    params = {
        "resource": "bdtopo-osrm",
        "start": f"{lon1},{lat1}",
        "end": f"{lon2},{lat2}",
        "profile": "car",
        "optimization": "fastest",
        "distanceUnit": "kilometer",
        "timeUnit": "minute",
        "getSteps": "false",
        "getBbox": "false",
    }
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    logger.debug("[route] %.4f,%.4f → %.4f,%.4f", lat1, lon1, lat2, lon2)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                API_URL, params=params,
                timeout=aiohttp.ClientTimeout(total=15), ssl=ssl_ctx,
            ) as response:
                response.raise_for_status()
                data = await response.json()
    except aiohttp.ClientError as e:
        return {"error": f"Erreur requête : {e!s}"}

    try:
        return {
            "distance_km": round(float(data["distance"]), 3),
            "duree_minutes": round(float(data["duration"]), 2),
        }
    except (KeyError, ValueError) as e:
        return {"error": f"Réponse inattendue de l'API : {e!s}"}


# ---------------------------------------------------------------------------
# Agent setup
# ---------------------------------------------------------------------------

TOOLS = [
    query_hikes_database,
    address_to_location_tool,
    calcul_distance_vol_oiseau,
    calculer_itineraire_routier,
    scraper_tool,
]

llm_gpt5_mini = ChatOpenAI(model="gpt-5-mini", temperature=0)
llm_gpt5_nano = ChatOpenAI(model="gpt-5-nano", temperature=0).with_structured_output(
    AgentAnswer
)

# Build system prompt with injected hike data
_hikes_summary = _build_hikes_summary()

SYSTEM_MESSAGE = (
    "Tu es Neorando, un agent IA expert des randonnées autour de Grenoble.\n\n"
    "## Données disponibles\n"
    f"{_hikes_summary}\n\n"
    "## Instructions\n"
    "1. TOUJOURS chercher d'abord la réponse dans la base de données ci-dessus.\n"
    "2. Utilise `query_hikes_database` pour filtrer, trier et agréger les données.\n"
    "3. Pour les questions géographiques (distance à vol d'oiseau, itinéraire routier) :\n"
    "   - Les coordonnées GPS des points de départ sont dans la base de données (champs latitude, longitude).\n"
    "   - Utilise `address_to_location_tool` pour géocoder un lieu externe (gare, place, ville...).\n"
    "   - Utilise `calcul_distance_vol_oiseau` pour la distance en ligne droite.\n"
    "   - Utilise `calculer_itineraire_routier` pour la distance/durée en voiture.\n"
    "4. N'utilise `scraper_tool` QUE si l'info n'est pas dans la base de données.\n"
    "5. Sois concis et précis. Donne UNIQUEMENT la valeur demandée, sans phrase.\n"
    "6. Pour les nombres, donne la valeur numérique exacte (pas d'arrondi inutile).\n"
    "7. Pour les listes, donne les noms exacts des randonnées tels qu'ils apparaissent dans la base.\n"
)

agent = create_agent(
    llm_gpt5_mini, tools=TOOLS, system_prompt=SYSTEM_MESSAGE, debug=False
)


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

        formatting_prompt = HumanMessage(
            content=(
                f"Question originale : {question}\n\n"
                f"Réponse de l'agent : {last_message.content}\n\n"
                "En te basant sur la question et la réponse ci-dessus, "
                "remplis EXACTEMENT UN des quatre champs selon le type de question :\n"
                " - `answer`  → réponse textuelle (nom de randonnée, commune, point de départ, …)\n"
                " - `numeric` → valeur numérique (distance, durée, nombre, dénivelé, …)\n"
                " - `boolean` → oui / non\n"
                " - `items`   → liste ordonnée de chaînes de caractères (noms de randonnées, communes, …)\n"
                "IMPORTANT : ne mets que la valeur brute, pas de phrase."
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
