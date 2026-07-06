"""
MDBList API client for fetching aggregated multi-source ratings.

MDBList (https://mdblist.com) aggregates IMDb, TMDb, Trakt, Rotten Tomatoes
(critic + audience), Metacritic, Letterboxd and more for BOTH movies and TV
shows, keyed by TMDb/IMDb/TVDb id. Unlike OMDb, its Rotten Tomatoes and
Metacritic coverage for series is reliable, which is why the wider
Plex/*arr ecosystem (Kometa, RPDB, Stremio) uses it as the canonical
multi-source ratings provider.

The API returns a ``ratings`` list where each entry has a ``score`` field
normalised to 0-100 across every source, which this client maps onto the
SuggestArr rating columns.
"""

from __future__ import annotations

from typing import Any, Optional

import aiohttp

from api_service.config.logger_manager import LoggerManager
from api_service.services.http.base_client import BaseHTTPClient

HTTP_OK = {200, 201}


def _score_to_ten(score: Any) -> Optional[float]:
    """Convert an MDBList 0-100 ``score`` to a 0-10 rating (1 decimal)."""
    if score in (None, ''):
        return None
    try:
        return round(float(score) / 10.0, 1)
    except (TypeError, ValueError):
        return None


def _score_to_percent(score: Any) -> Optional[int]:
    """Convert an MDBList 0-100 ``score`` to an integer percentage."""
    if score in (None, ''):
        return None
    try:
        return int(round(float(score)))
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> Optional[int]:
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _index_ratings(payload: dict) -> dict[str, dict]:
    """Index an MDBList ``ratings`` list by source name (dropping null scores)."""
    indexed: dict[str, dict] = {}
    for entry in (payload or {}).get('ratings') or []:
        source = (entry or {}).get('source')
        if source:
            indexed[source] = entry
    return indexed


def parse_mdblist_ratings(payload: dict) -> dict:
    """Map an MDBList media-info payload onto SuggestArr rating fields.

    Uses the normalised ``score`` (0-100) for every source so scales are
    consistent regardless of the per-source ``value`` scale.
    """
    ratings = _index_ratings(payload)

    def score(source: str) -> Any:
        return (ratings.get(source) or {}).get('score')

    def votes(source: str) -> Any:
        return (ratings.get(source) or {}).get('votes')

    ids = (payload or {}).get('ids') or {}

    return {
        'imdb_id': ids.get('imdb'),
        'imdb_rating': _score_to_ten(score('imdb')),
        'imdb_votes': _to_int(votes('imdb')),
        'rt_rating': _score_to_percent(score('tomatoes')),
        'rt_user_rating': _score_to_percent(score('popcorn')),
        'metacritic_rating': _score_to_percent(score('metacritic')),
        'trakt_rating': _score_to_ten(score('trakt')),
        'trakt_votes': _to_int(votes('trakt')),
        'rating': _score_to_ten(score('tmdb')),
    }


class MdbListClient(BaseHTTPClient):
    """Client for the MDBList API's aggregated ratings endpoint."""

    def __init__(self, api_key: str):
        """
        Initialize the MdbListClient.

        Args:
            api_key (str): MDBList API key (free tier at mdblist.com).
        """
        super().__init__()
        self.api_key = api_key
        self.base_url = "https://api.mdblist.com"
        self.logger.debug("MdbListClient initialized")

    async def get_ratings(self, media_type: str, tmdb_id: str | int) -> Optional[dict]:
        """
        Fetch aggregated multi-source ratings for a TMDb item.

        Args:
            media_type (str): 'movie' or 'tv'.
            tmdb_id (str | int): The TMDb id of the item.

        Returns:
            dict | None: Mapped rating fields (imdb/rt/rt_user/metacritic/trakt/
                         tmdb) or None when unavailable or the request fails.
        """
        if not self.api_key or tmdb_id in (None, ''):
            return None

        provider_type = 'show' if media_type == 'tv' else 'movie'
        url = f"{self.base_url}/tmdb/{provider_type}/{tmdb_id}?apikey={self.api_key}"
        self.logger.debug("Fetching MDBList ratings for %s tmdb:%s", media_type, tmdb_id)

        try:
            session = await self._get_session()
            async with session.get(url, timeout=self.REQUEST_TIMEOUT) as response:
                if response.status == 404:
                    self.logger.debug("MDBList has no entry for %s tmdb:%s", media_type, tmdb_id)
                    return None
                if response.status not in HTTP_OK:
                    self.logger.warning(
                        "MDBList request failed for %s tmdb:%s: HTTP %d",
                        media_type, tmdb_id, response.status,
                    )
                    return None
                data = await response.json()
        except aiohttp.ClientError as exc:
            self.logger.warning(
                "MDBList request error for %s tmdb:%s: %s",
                media_type, tmdb_id, str(exc).replace(self.api_key, "***"),
            )
            return None

        if not isinstance(data, dict) or data.get('error'):
            return None

        parsed = parse_mdblist_ratings(data)
        self.logger.debug(
            "MDBList ratings for %s tmdb:%s: imdb=%s rt=%s rt_user=%s mc=%s trakt=%s tmdb=%s",
            media_type, tmdb_id,
            parsed['imdb_rating'], parsed['rt_rating'], parsed['rt_user_rating'],
            parsed['metacritic_rating'], parsed['trakt_rating'], parsed['rating'],
        )
        return parsed
