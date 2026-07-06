"""Anime detection helpers for Seer profile routing."""

from typing import Any, Dict, Iterable

ANIMATION_GENRE_ID = 16
ANIME_KEYWORDS = {"anime", "japanese animation"}
JAPANESE_LANGUAGE = "ja"
JAPAN_COUNTRY_CODES = {"JP"}


def _names(values: Iterable[Any]) -> set[str]:
    """Normalize TMDb keyword/name payloads to lowercase names."""
    names = set()
    for value in values or []:
        if isinstance(value, dict):
            text = value.get("name") or value.get("label")
        else:
            text = value
        if text is not None:
            names.add(str(text).strip().lower())
    return names


def _country_codes(item: Dict[str, Any]) -> set[str]:
    """Return normalized TMDb origin/production country codes."""
    codes = set()
    for key in ("origin_country", "production_countries"):
        for value in item.get(key) or []:
            if isinstance(value, dict):
                code = value.get("iso_3166_1")
            else:
                code = value
            if code is not None:
                codes.add(str(code).strip().upper())
    return codes


def is_anime_media(item: Dict[str, Any]) -> bool:
    """Return True when a TMDb item should use anime profile routing."""
    if not isinstance(item, dict):
        return False

    keyword_names = _names(item.get("keywords") or item.get("keyword_names") or [])
    if keyword_names.intersection(ANIME_KEYWORDS):
        return True

    genre_ids = {
        int(genre_id)
        for genre_id in item.get("genre_ids") or []
        if str(genre_id).isdigit()
    }
    if ANIMATION_GENRE_ID not in genre_ids:
        return False

    original_language = str(item.get("original_language") or "").strip().lower()
    if original_language == JAPANESE_LANGUAGE:
        return True

    return bool(_country_codes(item).intersection(JAPAN_COUNTRY_CODES))
