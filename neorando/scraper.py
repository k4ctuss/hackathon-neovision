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
    """Parse a detail page HTML into a structured hike dict.

    Uses the structured DOM (dl/dt/dd in track-section and strucutre-adresse)
    rather than fragile line-by-line text parsing.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Detect 404 pages
    if soup.find(string=re.compile(r"page.*introuvable|n.a pas été trouvée", re.I)):
        return {}

    # Name (collapse multiple spaces)
    h1 = soup.find("h1")
    name = " ".join((h1.get_text(strip=True) if h1 else "").split())

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

    # ------------------------------------------------------------------
    # 1) Characteristics from the track-section <dl>
    # ------------------------------------------------------------------
    track_section = soup.find("div", class_="track-section")
    if track_section:
        dl = track_section.find("dl")
        if dl:
            dts = dl.find_all("dt")
            dds = dl.find_all("dd")
            for dt, dd in zip(dts, dds):
                label = dt.get_text(strip=True).lower()
                value = dd.get_text(strip=True)

                if "distance" in label:
                    hike["distance_km"] = _parse_float(value)

                elif "nivellation positive" in label or "nivelé positif" in label:
                    hike["denivele_positif_m"] = _parse_float(value)

                elif "nivellation négative" in label or "nivelé négatif" in label:
                    hike["denivele_negatif_m"] = _parse_float(value)

                elif "durée" in label or "duree" in label:
                    hike["duree_min"] = _parse_duration_minutes(value)

                elif "niveau" in label:
                    # e.g. "Niveau noir - Très difficile", "Niveau bleu - Facile"
                    m = re.search(r"[-–]\s*(.+)", value)
                    diff = m.group(1).strip() if m else value.strip()
                    # Normalize: keep only the main difficulty level
                    # e.g. "Facile, Adapté aux débutants" → "Facile"
                    diff = diff.split(",")[0].strip()
                    hike["difficulte"] = diff

                elif "type" in label:
                    hike["type_parcours"] = value.strip()

    # ------------------------------------------------------------------
    # 2) Address section (class="strucutre-adresse" — typo in site HTML)
    # ------------------------------------------------------------------
    addr_div = soup.find("div", class_="strucutre-adresse")
    if addr_div:
        first_dd = addr_div.find("dd")
        if first_dd:
            # Departure: look for <p> containing "Départ"
            for p in first_dd.find_all("p"):
                p_text = p.get_text(strip=True)
                depart_match = re.split(r"[Dd]épart\s*:?\s*", p_text)
                if len(depart_match) > 1 and depart_match[-1].strip():
                    hike["depart"] = depart_match[-1].strip()
                    break
            # If no explicit "Départ" label, second <p> is often the departure
            if not hike["depart"]:
                ps = first_dd.find_all("p")
                if len(ps) >= 2:
                    candidate = ps[1].get_text(strip=True)
                    if candidate and len(candidate) < 100:
                        hike["depart"] = candidate

            # Commune: from the bare text "38xxx COMMUNE-NAME"
            dd_text = first_dd.get_text(separator="\n", strip=True)
            for line in dd_text.split("\n"):
                zip_match = re.match(r"(\d{5})\s+(.+)", line.strip())
                if zip_match and zip_match.group(1).startswith("38"):
                    hike["commune"] = zip_match.group(2).strip()
                    break

    # ------------------------------------------------------------------
    # 3) Animaux — look in <li> tags
    # ------------------------------------------------------------------
    for li in soup.find_all("li"):
        li_text = li.get_text(strip=True).lower()
        if "animaux acceptés" in li_text or "animaux autorisés" in li_text:
            hike["animaux_acceptes"] = True
            break
        elif "animaux refusés" in li_text or "animaux non" in li_text or "animaux interdits" in li_text:
            hike["animaux_acceptes"] = False
            break

    # ------------------------------------------------------------------
    # 4) GPS coordinates — from Google Maps link, scripts, or meta tags
    # ------------------------------------------------------------------
    # Best source: the Google Maps link in the address section
    gps_link = soup.find("a", class_="gps", href=True)
    if gps_link:
        coords_match = re.search(r"daddr=([\d.]+),([\d.]+)", gps_link["href"])
        if coords_match:
            hike["latitude"] = float(coords_match.group(1))
            hike["longitude"] = float(coords_match.group(2))

    # Fallback: scripts with JSON latitude/longitude
    if not hike["latitude"]:
        for script in soup.find_all("script"):
            st = script.string or ""
            lat_m = re.search(r'"latitude"[:\s]*([\d.]+)', st)
            lon_m = re.search(r'"longitude"[:\s]*([\d.]+)', st)
            if lat_m and lon_m:
                hike["latitude"] = float(lat_m.group(1))
                hike["longitude"] = float(lon_m.group(1))
                break

    # Fallback: meta tags
    if not hike["latitude"]:
        for meta in soup.find_all("meta"):
            content = meta.get("content", "")
            prop = str(meta.get("property", "")).lower()
            if "latitude" in prop:
                hike["latitude"] = _parse_float(content)
            if "longitude" in prop:
                hike["longitude"] = _parse_float(content)

    # ------------------------------------------------------------------
    # 5) Fallback commune from full text if not found in address section
    # ------------------------------------------------------------------
    if not hike["commune"]:
        full_text = soup.get_text(separator="\n", strip=True)
        commune_match = re.search(r"(\d{5})\s+([A-ZÀ-Ü\s\-]{3,40})", full_text)
        if commune_match:
            hike["commune"] = commune_match.group(2).strip()

    return hike


def _stub_from_url(url: str) -> dict:
    """Create a minimal hike entry from the URL slug when the page is unavailable."""
    slug = url.rstrip("/").split("/")[-1]
    # Remove trailing numeric ID
    name = re.sub(r"-\d+$", "", slug)
    # Humanize: hyphens → spaces, title case
    name = name.replace("-", " ").strip()
    # Fix common French elisions (l-xxx → l'xxx, d-xxx → d'xxx)
    name = re.sub(r"\b([ldLD]) ", r"\1'", name)
    name = name[0].upper() + name[1:] if name else name
    return {
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
                        logger.warning("HTTP %s for %s — creating stub entry", resp.status if resp else "None", url)
                        return _stub_from_url(url)
                    try:
                        await page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass
                    html = await page.content()
                    result = parse_hike_page(html, url)
                    # 404 soft pages return empty dict
                    return result if result.get("name") else _stub_from_url(url)
                except Exception as e:
                    logger.error("Error scraping %s: %s — creating stub entry", url, e)
                    return _stub_from_url(url)
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
