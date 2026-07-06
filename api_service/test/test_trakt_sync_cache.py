from unittest.mock import AsyncMock, MagicMock

import pytest

from api_service.services.trakt import sync_cache


@pytest.fixture(autouse=True)
def clear_cache():
    sync_cache.clear_sync_cache()
    yield
    sync_cache.clear_sync_cache()


@pytest.mark.asyncio
async def test_warm_user_sync_cache_fetches_lists_once():
    client = MagicMock()
    client._request = AsyncMock(side_effect=[
        [{"movie": {"ids": {"tmdb": 550}}}],
        [],
        [{"rating": 8, "movie": {"ids": {"tmdb": 550}}}],
        [],
    ])

    first = await sync_cache.warm_user_sync_cache(client, "jf-1")
    second = await sync_cache.warm_user_sync_cache(client, "jf-1")

    assert first is second
    assert client._request.await_count == 4


@pytest.mark.asyncio
async def test_lookup_item_status_uses_snapshot():
    snapshot = sync_cache._UserSyncSnapshot(
        watched_movies=[{"movie": {"ids": {"tmdb": 550}}}],
        watched_shows=[],
        ratings_movies=[{"rating": 9, "movie": {"ids": {"tmdb": 550}}}],
        ratings_shows=[],
        fetched_at=0,
    )

    status = sync_cache.lookup_item_status(snapshot, "movie", "550")

    assert status == {"watched": True, "rating": 9}


@pytest.mark.asyncio
async def test_invalidate_user_sync_cache_forces_refresh():
    client = MagicMock()
    client._request = AsyncMock(side_effect=[
        [], [], [], [],
        [{"movie": {"ids": {"tmdb": 1}}}], [], [], [],
    ])

    await sync_cache.warm_user_sync_cache(client, "jf-1")
    sync_cache.invalidate_user_sync_cache("jf-1")
    await sync_cache.warm_user_sync_cache(client, "jf-1")

    assert client._request.await_count == 8
