"""Pre-scrape all hike data from grenoble-tourisme.com and cache as JSON."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

logger = logging.getLogger(__name__)

SOURCE_URL = "https://www.grenoble-tourisme.com/fr/faire/randonner/a-pied/"
CACHE_PATH = Path(__file__).parent.parent / "data" / "hikes.json"

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# Semaphore to limit concurrent page loads
MAX_CONCURRENT = 4


async def get_all_hike_urls() -> list[str]:
    """Scrape all hike detail URLs from the listing pages."""
    urls: set[str] = set()
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=BROWSER_UA,
            locale="fr-FR",
        )
        page = await context.new_page()
        await Stealth().apply_stealth_async(page)

        for page_num in range(1, 5):  # 3 pages expected, 4 for safety
            list_url = f"{SOURCE_URL}?page={page_num}" if page_num > 1 else SOURCE_URL
            logger.info("Listing page %d: %s", page_num, list_url)
            try:
                resp = await page.goto(list_url, wait_until="domcontentloaded", timeout=30000)
                if resp and resp.status == 200:
                    try:
                        await page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass
                    html = await page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    found = 0
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "/catalogue/detail/" in href:
                            full = urljoin("https://www.grenoble-tourisme.com", href)
                            if full not in urls:
                                found += 1
                            urls.add(full)
                    logger.info("  → %d new URLs (total: %d)", found, len(urls))
                    if found == 0 and page_num > 1:
                        break
            except Exception as e:
                logger.error("Error on listing page %d: %s", page_num, e)

        await browser.close()

    logger.info("Total unique hike URLs: %d", len(urls))
    return sorted(urls)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_float(text: str) -> float | None:
    text = text.replace(",", ".").replace("\xa0", "").strip()
    m = re.search(r"([\d]+(?:\.[\d]+)?)", text)
    return float(m.group(1)) if m else None


def _parse_duration_minutes(text: str) -> float | None:
    text = text.lower().strip()
    hours = minutes = 0
    h = re.search(r"(\d+)\s*h", text)
    m = re.search(r"(\d+)\s*min", text)
    d = re.search(r"(\d+)\s*jour", text)
    if h:
        hours = int(h.group(1))
    if m:
        minutes = int(m.group(1))
    if d and not h:
        return int(d.group(1)) * 480  # ~8h/day
    total = hours * 60 + minutes
    return total if total > 0 else None


def parse_hike_page(html: str, url: str) -> dict:
    """Parse a detail page HTML into a structured hike dict."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove noise
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe"]):
        tag.decompose()

    # Name
    h1 = soup.find("h1")
    name = h1.get_text(strip=True) if h1 else ""

    hike: dict = {
        "name": name,
        "url": url,
        "commune": None,
        "depart": None,
        "distance_km": None,
        "duree_min": None,
        "denivele_positif_m": None,
        "denivele_negatif_m": None,
        "difficulte": None,
        "type_parcours": None,
        "animaux_acceptes": None,
        "latitude": None,
        "longitude": None,
    }

    full_text = soup.get_text(separator="\n", strip=True)
    lines = full_text.split("\n")

    for i, line in enumerate(lines):
        lo = line.lower().strip()

        # Commune — often after a label or near zip code
        if not hike["commune"]:
            # Pattern: "COMMUNE (38xxx)" or just commune name near zip
            zip_match = re.search(r"(\d{5})\s+(.+)", line.strip())
            if zip_match and zip_match.group(1).startswith("38"):
                hike["commune"] = zip_match.group(2).strip()
            elif re.match(r"^[A-Z\s\-]+$", line.strip()) and len(line.strip()) > 2 and len(line.strip()) < 40:
                # All-caps line might be commune name (like "CORENC")
                if i > 0 and any(kw in lines[i - 1].lower() for kw in ["commune", "localisation"]):
                    hike["commune"] = line.strip().title()

        # Distance
        if "distance" in lo and not hike["distance_km"]:
            val = _parse_float(lo.split("distance")[-1])
            if val and val < 500:
                hike["distance_km"] = val
        elif not hike["distance_km"]:
            km_match = re.match(r"^([\d,\.]+)\s*km$", line.strip())
            if km_match:
                hike["distance_km"] = _parse_float(km_match.group(1))

        # Duration
        if ("durée" in lo or "duree" in lo) and not hike["duree_min"]:
            hike["duree_min"] = _parse_duration_minutes(lo)
        elif not hike["duree_min"] and re.match(r"^\d+\s*h(\s*\d+)?$", line.strip().lower()):
            hike["duree_min"] = _parse_duration_minutes(line)

        # Dénivelé positif
        if "dénivellation positive" in lo or "dénivelé positif" in lo or "denivele positif" in lo:
            val = _parse_float(lo)
            if val:
                hike["denivele_positif_m"] = val
        elif "dénivellation" in lo and "positif" in lo:
            val = _parse_float(lo)
            if val:
                hike["denivele_positif_m"] = val

        # Dénivelé négatif
        if "dénivellation négative" in lo or "dénivelé négatif" in lo:
            val = _parse_float(lo)
            if val:
                hike["denivele_negatif_m"] = val

        # Difficulté
        if "niveau" in lo and not hike["difficulte"]:
            diff_match = re.search(r"niveau\s+\w+\s*[-–]\s*(\w+)", lo)
            if diff_match:
                hike["difficulte"] = diff_match.group(1).capitalize()

        # Type de parcours
        if not hike["type_parcours"]:
            for tp in ["boucle", "aller-retour", "itinérance", "aller retour"]:
                if tp in lo:
                    hike["type_parcours"] = tp.replace("aller retour", "Aller-retour").title()
                    break

        # Point de départ
        if ("départ" in lo or "depart" in lo) and not hike["depart"]:
            parts = re.split(r"(?:départ|depart)\s*:?\s*", line, flags=re.IGNORECASE)
            if len(parts) > 1 and parts[-1].strip():
                hike["depart"] = parts[-1].strip()

        # Animaux
        if "animaux acceptés" in lo or "animaux autorisés" in lo:
            hike["animaux_acceptes"] = True
        elif "animaux refusés" in lo or "animaux non" in lo or "animaux interdits" in lo:
            hike["animaux_acceptes"] = False

    # GPS — look in the original HTML (before decompose), so re-parse
    raw_soup = BeautifulSoup(html, "html.parser")
    for script in raw_soup.find_all("script"):
        st = script.string or ""
        lat_m = re.search(r'"latitude"[:\s]*([\d.]+)', st)
        lon_m = re.search(r'"longitude"[:\s]*([\d.]+)', st)
        if lat_m and lon_m:
            hike["latitude"] = float(lat_m.group(1))
            hike["longitude"] = float(lon_m.group(1))
            break

    # Also check meta tags and data attributes
    if not hike["latitude"]:
        for meta in raw_soup.find_all("meta"):
            content = meta.get("content", "")
            if "latitude" in str(meta.get("property", "")).lower():
                hike["latitude"] = _parse_float(content)
            if "longitude" in str(meta.get("property", "")).lower():
                hike["longitude"] = _parse_float(content)

    # Check for geo coordinates in text
    if not hike["latitude"]:
        geo_match = re.search(
            r"latitude[:\s]*([\d.]+).*?longitude[:\s]*([\d.]+)",
            full_text,
            re.IGNORECASE | re.DOTALL,
        )
        if geo_match:
            hike["latitude"] = float(geo_match.group(1))
            hike["longitude"] = float(geo_match.group(2))

    # Fallback commune detection from text
    if not hike["commune"]:
        commune_match = re.search(r"(\d{5})\s+([A-ZÀ-Ü\s\-]+)", full_text)
        if commune_match:
            hike["commune"] = commune_match.group(2).strip().title()

    return hike


# ---------------------------------------------------------------------------
# Batch scraping
# ---------------------------------------------------------------------------


async def scrape_all_hikes(urls: list[str] | None = None) -> list[dict]:
    """Scrape all hike detail pages and return structured data."""
    if urls is None:
        urls = await get_all_hike_urls()

    hikes: list[dict] = []
    sem = asyncio.Semaphore(MAX_CONCURRENT)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )

        async def scrape_one(url: str) -> dict | None:
            async with sem:
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent=BROWSER_UA,
                    locale="fr-FR",
                )
                page = await context.new_page()
                await Stealth().apply_stealth_async(page)
                try:
                    resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    if not resp or resp.status != 200:
                        logger.warning("HTTP %s for %s", resp.status if resp else "None", url)
                        return None
                    try:
                        await page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass
                    html = await page.content()
                    return parse_hike_page(html, url)
                except Exception as e:
                    logger.error("Error scraping %s: %s", url, e)
                    return None
                finally:
                    await context.close()

        tasks = [scrape_one(u) for u in urls]
        results = await asyncio.gather(*tasks)
        for r in results:
            if r and r.get("name"):
                hikes.append(r)

        await browser.close()

    logger.info("Successfully scraped %d / %d hikes", len(hikes), len(urls))
    return hikes


def save_hikes(hikes: list[dict], path: Path = CACHE_PATH) -> None:
    """Save scraped hikes to JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(hikes, f, ensure_ascii=False, indent=2)
    logger.info("Saved %d hikes to %s", len(hikes), path)


def load_hikes(path: Path = CACHE_PATH) -> list[dict]:
    """Load cached hikes from JSON."""
    if not path.exists():
        raise FileNotFoundError(
            f"Hike cache not found at {path}. Run 'uv run neorando scrape' first."
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


async def scrape_and_save() -> list[dict]:
    """Full pipeline: scrape all hikes and save to cache."""
    hikes = await scrape_all_hikes()
    save_hikes(hikes)
    return hikes
