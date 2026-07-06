"""Tests for multi-source rating enrichment and caching."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from api_service.services.ratings.enrichment import (
    clear_run_ratings_cache,
    enrich_media_ratings,
)


class TestRatingsEnrichment(unittest.IsolatedAsyncioTestCase):
  def setUp(self):
    clear_run_ratings_cache()

  async def test_uses_fresh_db_cache_without_external_calls(self):
    db_manager = MagicMock()
    fresh_at = datetime.now(timezone.utc).isoformat()
    db_manager.get_metadata_ratings.return_value = {
      'imdb_id': 'tt123',
      'imdb_rating': 8.1,
      'imdb_votes': 1000,
      'rt_rating': 87,
      'metacritic_rating': 74,
      'trakt_rating': 8.0,
      'trakt_votes': 500,
      'ratings_updated_at': fresh_at,
    }
    tmdb_client = MagicMock()
    tmdb_client.omdb_client = MagicMock()
    tmdb_client.omdb_client.get_rating = AsyncMock()

    media = {'id': '550'}
    result = await enrich_media_ratings(
      media,
      'movie',
      tmdb_client=tmdb_client,
      db_manager=db_manager,
    )

    self.assertEqual(result['imdb_rating'], 8.1)
    self.assertEqual(result['rt_rating'], 87)
    tmdb_client.omdb_client.get_rating.assert_not_called()
    db_manager.update_metadata_ratings.assert_not_called()

  async def test_fetches_and_persists_on_stale_cache(self):
    db_manager = MagicMock()
    stale_at = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    db_manager.get_metadata_ratings.return_value = {
      'imdb_id': 'tt123',
      'imdb_rating': 7.0,
      'imdb_votes': 10,
      'rt_rating': None,
      'metacritic_rating': None,
      'trakt_rating': None,
      'trakt_votes': None,
      'ratings_updated_at': stale_at,
    }

    tmdb_client = MagicMock()
    tmdb_client._get_item_details = AsyncMock(return_value={'imdb_id': 'tt123'})
    tmdb_client.omdb_client = MagicMock()
    tmdb_client.omdb_client.get_rating = AsyncMock(return_value={
      'imdb_rating': 8.2,
      'imdb_votes': 2000,
      'rt_rating': 91,
      'metacritic_rating': 80,
    })

    trakt_client = MagicMock()
    trakt_client.get_community_rating = AsyncMock(return_value={
      'trakt_rating': 8.5,
      'trakt_votes': 120,
    })

    with patch('api_service.services.ratings.enrichment.load_env_vars', return_value={'RATINGS_CACHE_TTL_HOURS': 24}):
      media = {'id': '550', 'title': 'Fight Club'}
      result = await enrich_media_ratings(
        media,
        'movie',
        tmdb_client=tmdb_client,
        db_manager=db_manager,
        trakt_client=trakt_client,
      )

    self.assertEqual(result['imdb_rating'], 8.2)
    self.assertEqual(result['rt_rating'], 91)
    self.assertEqual(result['trakt_rating'], 8.5)
    db_manager.update_metadata_ratings.assert_called_once()

  async def test_in_run_cache_dedupes_repeated_items(self):
    db_manager = MagicMock()
    db_manager.get_metadata_ratings.return_value = None

    tmdb_client = MagicMock()
    tmdb_client._get_item_details = AsyncMock(return_value={'imdb_id': 'tt123'})
    tmdb_client.omdb_client = MagicMock()
    tmdb_client.omdb_client.get_rating = AsyncMock(return_value={
      'imdb_rating': 8.0,
      'imdb_votes': 100,
      'rt_rating': 80,
      'metacritic_rating': 70,
    })

    with patch('api_service.services.ratings.enrichment.load_env_vars', return_value={'RATINGS_CACHE_TTL_HOURS': 24}):
      media = {'id': '550', 'title': 'Fight Club'}
      await enrich_media_ratings(media, 'movie', tmdb_client=tmdb_client, db_manager=db_manager)
      await enrich_media_ratings({'id': '550', 'title': 'Fight Club'}, 'movie', tmdb_client=tmdb_client, db_manager=db_manager)

    self.assertEqual(tmdb_client.omdb_client.get_rating.await_count, 1)

if __name__ == '__main__':
  unittest.main()
