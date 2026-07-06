"""
OMDb API client for fetching IMDB ratings.

The OMDb API (Open Movie Database) provides IMDB rating data
using IMDB IDs (tt... format).
"""

import re

import aiohttp
from api_service.services.http.base_client import BaseHTTPClient
from api_service.config.logger_manager import LoggerManager

HTTP_OK = {200, 201}


def _parse_int_rating(value) -> int | None:
    """Parse a numeric rating from OMDb strings like '87%' or '74/100'."""
    if value in (None, '', 'N/A'):
        return None
    text = str(value).strip()
    if '/' in text:
        text = text.split('/', 1)[0]
    text = text.rstrip('%').strip()
    try:
        return int(float(text))
    except (ValueError, TypeError):
        return None


def _parse_omdb_ratings(data: dict) -> dict:
    """Extract IMDB, Rotten Tomatoes, and Metacritic ratings from an OMDb payload."""
    raw_rating = data.get('imdbRating')
    raw_votes = data.get('imdbVotes')
    rating_missing = raw_rating in (None, '', 'N/A')
    votes_missing = raw_votes in (None, '', 'N/A')

    imdb_votes = None
    if not votes_missing:
        try:
            imdb_votes = int(str(raw_votes).replace(',', ''))
        except (ValueError, TypeError):
            imdb_votes = None

    imdb_rating = None
    if not rating_missing:
        try:
            imdb_rating = float(raw_rating)
        except (ValueError, TypeError):
            imdb_rating = None

    rt_rating = None
    rt_user_rating = _parse_int_rating(data.get('tomatoUserMeter'))
    metacritic_rating = _parse_int_rating(data.get('Metascore'))
    for entry in data.get('Ratings') or []:
        source = (entry or {}).get('Source')
        value = (entry or {}).get('Value')
        if source == 'Rotten Tomatoes':
            rt_rating = _parse_int_rating(value)
        elif source in ('Rotten Tomatoes Audience', 'Rotten Tomatoes User'):
            rt_user_rating = _parse_int_rating(value)
        elif source == 'Metacritic' and metacritic_rating is None:
            metacritic_rating = _parse_int_rating(value)

    if rt_rating is None:
        rt_rating = _parse_int_rating(data.get('tomatoMeter'))

    return {
        'imdb_rating': imdb_rating,
        'imdb_votes': imdb_votes,
        'imdb_rating_raw': raw_rating,
        'rt_rating': rt_rating,
        'rt_user_rating': rt_user_rating,
        'metacritic_rating': metacritic_rating,
    }


_RT_AUDIENCE_RE = re.compile(r'"audienceScore":\{[^}]*"score":"(\d+)"')
_RT_USER_AGENT = 'Mozilla/5.0 (compatible; SuggestArr/1.0)'


class OmdbClient(BaseHTTPClient):
    """
    Client for interacting with the OMDb API to retrieve IMDB ratings.

    Uses the free OMDb API (https://www.omdbapi.com/) which returns
    IMDB ratings, vote counts, and other metadata by IMDB ID.
    """

    def __init__(self, api_key):
        """
        Initialize the OmdbClient.

        Args:
            api_key (str): OMDb API key (free tier at omdbapi.com).
        """
        super().__init__()
        self.api_key = api_key
        self.base_url = "https://www.omdbapi.com/"
        self.logger.debug("OmdbClient initialized")

    async def _fetch_rt_audience_score(self, rt_url: str) -> int | None:
        """Scrape Rotten Tomatoes audience score from a movie page URL."""
        if not rt_url or rt_url in ('N/A', ''):
            return None

        self.logger.debug("Fetching RT audience score from %s", rt_url)
        try:
            session = await self._get_session()
            headers = {'User-Agent': _RT_USER_AGENT}
            async with session.get(rt_url, headers=headers, timeout=self.REQUEST_TIMEOUT) as response:
                if response.status not in HTTP_OK:
                    self.logger.debug("RT page request failed for %s: HTTP %d", rt_url, response.status)
                    return None
                html = await response.text()
        except aiohttp.ClientError as exc:
            self.logger.debug("RT page request error for %s: %s", rt_url, exc)
            return None

        match = _RT_AUDIENCE_RE.search(html)
        if not match:
            return None
        return _parse_int_rating(match.group(1))

    def _tomato_url_matches(self, tomato_url: str, media_type: str | None) -> bool:
        """Return True when a tomatoURL is safe to scrape for ``media_type``.

        OMDb frequently returns a mismatched ``tomatoURL`` for series (e.g. the
        show *Friends* resolves to the 1994 movie ``/m/just_friends_1994/``).
        Scraping that page would attach an unrelated movie's audience score to
        the series, so reject cross-type URLs. When ``media_type`` is unknown we
        keep the legacy permissive behaviour.
        """
        if not media_type:
            return True
        path = str(tomato_url or '')
        if media_type == 'tv':
            return '/tv/' in path
        if media_type == 'movie':
            return '/m/' in path
        return True

    async def get_rating(self, imdb_id, media_type: str | None = None):
        """
        Fetch IMDB rating and vote count for a given IMDB ID.

        Args:
            imdb_id (str): IMDB ID in tt... format (e.g., 'tt0816692').
            media_type (str | None): 'movie' or 'tv'. Used to reject mismatched
                ``tomatoURL`` audience-score scrapes; ``None`` keeps legacy
                permissive behaviour.

        Returns:
            dict | None: Dictionary with imdb/rt/metacritic ratings and vote
                         counts, or None if unavailable or the request fails.
        """
        if not imdb_id or not self.api_key:
            return None

        url = f"{self.base_url}?i={imdb_id}&apikey={self.api_key}&tomatoes=true"
        self.logger.debug("Fetching OMDb rating for IMDB ID %s", imdb_id)

        try:
            session = await self._get_session()
            async with session.get(url, timeout=self.REQUEST_TIMEOUT) as response:
                if response.status in HTTP_OK:
                    data = await response.json()

                    if data.get('Response') == 'False':
                        self.logger.debug("OMDb returned no result for IMDB ID %s: %s",
                                          imdb_id, data.get('Error'))
                        return None

                    parsed = _parse_omdb_ratings(data)
                    if parsed['rt_user_rating'] is None:
                        tomato_url = data.get('tomatoURL')
                        if (
                            tomato_url
                            and tomato_url != 'N/A'
                            and self._tomato_url_matches(tomato_url, media_type)
                        ):
                            parsed['rt_user_rating'] = await self._fetch_rt_audience_score(tomato_url)
                        elif tomato_url and tomato_url != 'N/A':
                            self.logger.debug(
                                "Skipping mismatched tomatoURL for %s %s: %s",
                                media_type,
                                imdb_id,
                                tomato_url,
                            )
                    if parsed['imdb_rating'] is None:
                        self.logger.debug(
                            "No valid IMDB rating for IMDB ID %s (imdbRating=%s, imdbVotes=%s)",
                            imdb_id,
                            parsed['imdb_rating_raw'],
                            parsed['imdb_votes'],
                        )
                    else:
                        self.logger.debug(
                            "OMDb ratings for %s: IMDB %.1f, RT %s, RT user %s, Metacritic %s",
                            imdb_id,
                            parsed['imdb_rating'],
                            parsed['rt_rating'],
                            parsed['rt_user_rating'],
                            parsed['metacritic_rating'],
                        )
                    return parsed
                else:
                    self.logger.warning("OMDb request failed for IMDB ID %s: HTTP %d",
                                        imdb_id, response.status)
        except aiohttp.ClientError as e:
            self.logger.error("OMDb request error for IMDB ID %s: %s", imdb_id, str(e))

        return None
