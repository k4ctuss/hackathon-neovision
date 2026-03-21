"""Utility helpers shared across Neorando modules."""

from __future__ import annotations

import re
import unicodedata


def strip_accents(text: str) -> str:
    """Return text without diacritics (é -> e, ç -> c, etc.)."""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_for_filtering(value: str | None) -> str:
    """Normalize string for case- and accent-insensitive matching."""
    if value is None:
        return ""
    return strip_accents(value).lower().strip()


def normalize_scraped_text(value: str | None) -> str | None:
    """Normalize scraped text for consistent cache content."""
    if value is None:
        return None
    return strip_accents(value)


def extract_hike_id_from_url(url: str) -> int | None:
    """Extract numeric hike id from detail URL slug."""
    match = re.search(r"-(\d+)/?$", url)
    return int(match.group(1)) if match else None
