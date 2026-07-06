"""Tests for the MDBList aggregated-ratings client."""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from api_service.services.mdblist.mdblist_client import (
    MdbListClient,
    parse_mdblist_ratings,
)

# Real-shaped MDBList payload for Game of Thrones (a series OMDb returns
# almost no RT/Metacritic data for). ``score`` is normalised 0-100 for every
# source regardless of the per-source ``value`` scale.
_GOT_PAYLOAD = {
    "title": "Game of Thrones",
    "type": "show",
    "ids": {"imdb": "tt0944947", "trakt": 1390, "tmdb": 1399, "tvdb": 121361},
    "ratings": [
        {"source": "imdb", "value": 9.2, "score": 92, "votes": 2630633},
        {"source": "metacritic", "value": 86, "score": 86, "votes": 171},
        {"source": "metacriticuser", "value": 8.4, "score": 84.0, "votes": 20104},
        {"source": "trakt", "value": 88, "score": 88, "votes": 64214},
        {"source": "tomatoes", "value": 89, "score": 89, "votes": 337},
        {"source": "popcorn", "value": 85, "score": 85, "votes": None},
        {"source": "tmdb", "value": 84, "score": 84, "votes": 27165},
        {"source": "letterboxd", "value": None, "score": None, "votes": None},
    ],
}


class TestParseMdblistRatings(unittest.TestCase):
    def test_maps_scores_to_columns(self):
        parsed = parse_mdblist_ratings(_GOT_PAYLOAD)
        self.assertEqual(parsed["imdb_id"], "tt0944947")
        self.assertEqual(parsed["imdb_rating"], 9.2)   # score 92 -> /10
        self.assertEqual(parsed["imdb_votes"], 2630633)
        self.assertEqual(parsed["rt_rating"], 89)       # tomatoes (critic)
        self.assertEqual(parsed["rt_user_rating"], 85)  # popcorn (audience)
        self.assertEqual(parsed["metacritic_rating"], 86)
        self.assertEqual(parsed["trakt_rating"], 8.8)   # score 88 -> /10
        self.assertEqual(parsed["trakt_votes"], 64214)
        self.assertEqual(parsed["rating"], 8.4)         # tmdb score 84 -> /10

    def test_missing_sources_become_none(self):
        parsed = parse_mdblist_ratings({"ids": {}, "ratings": []})
        for key in ("imdb_rating", "rt_rating", "rt_user_rating",
                    "metacritic_rating", "trakt_rating", "rating"):
            self.assertIsNone(parsed[key])


class TestMdbListClient(unittest.IsolatedAsyncioTestCase):
    def _client_with_response(self, status, json_data):
        client = MdbListClient("key123")
        response = MagicMock()
        response.status = status
        response.json = AsyncMock(return_value=json_data)
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=response)
        ctx.__aexit__ = AsyncMock(return_value=False)
        session = MagicMock()
        session.get = MagicMock(return_value=ctx)
        client._get_session = AsyncMock(return_value=session)
        return client, session

    async def test_get_ratings_uses_show_path_for_tv(self):
        client, session = self._client_with_response(200, _GOT_PAYLOAD)
        result = await client.get_ratings("tv", "1399")
        self.assertEqual(result["metacritic_rating"], 86)
        self.assertEqual(result["rt_rating"], 89)
        called_url = session.get.call_args[0][0]
        self.assertIn("/tmdb/show/1399", called_url)

    async def test_get_ratings_movie_path(self):
        client, session = self._client_with_response(200, {"ids": {}, "ratings": []})
        await client.get_ratings("movie", "550")
        self.assertIn("/tmdb/movie/550", session.get.call_args[0][0])

    async def test_get_ratings_404_returns_none(self):
        client, _ = self._client_with_response(404, {"error": "Item not found"})
        self.assertIsNone(await client.get_ratings("tv", "999999999"))

    async def test_get_ratings_error_payload_returns_none(self):
        client, _ = self._client_with_response(200, {"error": "Item not found"})
        self.assertIsNone(await client.get_ratings("tv", "1"))

    async def test_no_api_key_returns_none(self):
        client = MdbListClient("")
        self.assertIsNone(await client.get_ratings("tv", "1399"))


if __name__ == "__main__":
    unittest.main()
