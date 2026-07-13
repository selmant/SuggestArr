"""Tests for Trakt recommendations job automation."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api_service.jobs.trakt_recommendations_automation import TraktRecommendationsAutomation


@pytest.mark.asyncio
async def test_fetch_trakt_recommendations_applies_max_results():
    automation = TraktRecommendationsAutomation()
    automation.job_data = {
        "media_type": "movie",
        "max_results": 2,
        "filters": {"ignore_collected": True, "ignore_watched": True},
    }
    automation.trakt_client = AsyncMock()
    automation.trakt_client.get_recommendations.return_value = [
        {"tmdb_id": "1", "title": "One", "media_type": "movie"},
        {"tmdb_id": "2", "title": "Two", "media_type": "movie"},
        {"tmdb_id": "3", "title": "Three", "media_type": "movie"},
    ]
    automation._should_skip_global_request = AsyncMock(return_value=False)
    automation._enrich_and_filter_item = AsyncMock(side_effect=lambda item: {
        "id": int(item["tmdb_id"]),
        "title": item["title"],
        "media_type": item["media_type"],
        "vote_average": 8.0,
        "vote_count": 1000,
    })

    results = await automation.fetch_trakt_recommendations()

    assert len(results) == 3
    automation.trakt_client.get_recommendations.assert_awaited_once_with(
        "movie",
        limit=250,
        ignore_collected=True,
        ignore_watched=True,
    )


@pytest.mark.asyncio
async def test_fetch_trakt_recommendations_skips_watched_titles_locally():
    automation = TraktRecommendationsAutomation()
    automation.job_data = {
        "media_type": "movie",
        "max_results": 2,
        "filters": {"ignore_watched": True},
    }
    automation.trakt_client = AsyncMock()
    automation.trakt_client.get_recommendations.return_value = [
        {"tmdb_id": "1", "title": "Watched", "media_type": "movie"},
        {"tmdb_id": "2", "title": "New", "media_type": "movie"},
    ]
    automation.watched_ids = {"movie": {"1"}, "tv": set()}
    automation._should_skip_global_request = AsyncMock(return_value=False)
    automation._enrich_and_filter_item = AsyncMock(side_effect=lambda item: item)

    results = await automation.fetch_trakt_recommendations()

    assert [item["tmdb_id"] for item in results] == ["2"]


@pytest.mark.asyncio
async def test_fetch_trakt_recommendations_requests_max_per_type_for_both():
    automation = TraktRecommendationsAutomation()
    automation.job_data = {
        "media_type": "both",
        "max_results": 30,
        "filters": {"ignore_collected": True, "ignore_watched": True},
    }
    automation.trakt_client = AsyncMock()
    automation.trakt_client.get_recommendations.return_value = []
    automation._should_skip_global_request = AsyncMock(return_value=False)
    automation._enrich_and_filter_item = AsyncMock(return_value=None)

    await automation.fetch_trakt_recommendations()

    assert automation.trakt_client.get_recommendations.await_count == 2
    automation.trakt_client.get_recommendations.assert_any_await(
        "movie",
        limit=250,
        ignore_collected=True,
        ignore_watched=True,
    )
    automation.trakt_client.get_recommendations.assert_any_await(
        "tv",
        limit=250,
        ignore_collected=True,
        ignore_watched=True,
    )


@pytest.mark.asyncio
async def test_fetch_trakt_recommendations_balances_movie_and_tv_targets():
    automation = TraktRecommendationsAutomation()
    automation.job_data = {
        "media_type": "both",
        "max_results": 30,
        "filters": {"ignore_collected": True, "ignore_watched": True},
    }
    automation.trakt_client = AsyncMock()

    async def get_recommendations_side_effect(item_type, **kwargs):
        count = 20 if item_type == "movie" else 20
        return [
            {"tmdb_id": str(1000 + index), "title": f"{item_type}-{index}", "media_type": item_type}
            for index in range(count)
        ]

    automation.trakt_client.get_recommendations.side_effect = get_recommendations_side_effect
    automation._should_skip_global_request = AsyncMock(return_value=False)
    automation._enrich_and_filter_item = AsyncMock(side_effect=lambda item: {
        "id": int(item["tmdb_id"]),
        "title": item["title"],
        "media_type": item["media_type"],
        "vote_average": 8.0,
        "vote_count": 1000,
    })

    results = await automation.fetch_trakt_recommendations()

    movie_count = sum(1 for item in results if item["media_type"] == "movie")
    tv_count = sum(1 for item in results if item["media_type"] == "tv")
    assert len(results) == 40
    assert movie_count == 20
    assert tv_count == 20


@pytest.mark.asyncio
async def test_fetch_trakt_recommendations_skips_already_requested_before_enriching():
    automation = TraktRecommendationsAutomation()
    automation.job_data = {
        "media_type": "movie",
        "max_results": 2,
        "filters": {"ignore_collected": True, "ignore_watched": True},
    }
    automation.trakt_client = AsyncMock()
    automation.trakt_client.get_recommendations.return_value = [
        {"tmdb_id": "1", "title": "One", "media_type": "movie"},
        {"tmdb_id": "2", "title": "Two", "media_type": "movie"},
        {"tmdb_id": "3", "title": "Three", "media_type": "movie"},
    ]

    async def skip_global_request(media_type, tmdb_id):
        return str(tmdb_id) in {"1", "2"}

    automation._should_skip_global_request = AsyncMock(side_effect=skip_global_request)
    automation._enrich_and_filter_item = AsyncMock(side_effect=lambda item: {
        "id": int(item["tmdb_id"]),
        "title": item["title"],
        "media_type": item["media_type"],
        "vote_average": 8.0,
        "vote_count": 1000,
    })

    results = await automation.fetch_trakt_recommendations()

    assert len(results) == 1
    assert results[0]["id"] == 3
    automation._enrich_and_filter_item.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_rejects_non_trakt_job():
    with patch("api_service.jobs.trakt_recommendations_automation.JobRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.get_job.return_value = {"id": 1, "job_type": "discover", "name": "Wrong"}

        with pytest.raises(ValueError, match="not a trakt_recommendations job"):
            await TraktRecommendationsAutomation.create(1)


@pytest.mark.asyncio
async def test_build_trakt_client_requires_single_linked_user():
    automation = TraktRecommendationsAutomation()
    automation.job_data = {"user_ids": []}
    automation.env_vars = {"SELECTED_SERVICE": "jellyfin"}
    automation.db_manager = MagicMock()

    with pytest.raises(ValueError, match="exactly one linked media user"):
        automation._build_trakt_client()


@pytest.mark.asyncio
async def test_fetch_tmdb_details_builds_full_image_urls():
    automation = TraktRecommendationsAutomation()
    automation.tmdb_client = MagicMock()
    automation.tmdb_client.tmdb_api_url = "https://api.themoviedb.org/3"
    automation.tmdb_client.api_key = "key"
    automation.tmdb_client.REQUEST_TIMEOUT = 10

    response = MagicMock()
    response.status = 200
    response.json = AsyncMock(return_value={
        "id": 27205,
        "title": "Inception",
        "vote_average": 8.8,
        "vote_count": 30000,
        "poster_path": "/inception.jpg",
        "backdrop_path": "/inception-bg.jpg",
        "overview": "A dream within a dream.",
        "release_date": "2010-07-16",
        "genres": [{"id": 28}],
        "original_language": "en",
    })

    class _Ctx:
        async def __aenter__(self):
            return response

        async def __aexit__(self, *args):
            return False

    session = MagicMock()
    session.get = MagicMock(return_value=_Ctx())
    automation.tmdb_client._get_session = AsyncMock(return_value=session)

    details = await automation._fetch_tmdb_details(27205, "movie")

    assert details["poster_path"] == "https://image.tmdb.org/t/p/w500/inception.jpg"
    assert details["backdrop_path"] == "https://image.tmdb.org/t/p/w1280/inception-bg.jpg"
    assert details["rating"] == 8.8


@pytest.mark.asyncio
async def test_enrich_and_filter_item_skips_excluded_streaming_provider():
    automation = TraktRecommendationsAutomation()
    automation.tmdb_client = MagicMock()
    automation.tmdb_client._apply_filters.return_value = {"passed": True}
    automation.tmdb_client.filter_min_runtime = None
    automation.tmdb_client.rating_source = "tmdb"
    automation.tmdb_client.omdb_client = None
    automation.tmdb_client.get_watch_providers = AsyncMock(return_value=(True, "Netflix"))

    item = {"media_type": "movie", "tmdb_id": "1", "title": "Blocked"}
    automation._fetch_tmdb_details = AsyncMock(return_value={
        "id": 1,
        "title": "Blocked",
        "vote_average": 8.0,
        "vote_count": 1000,
    })

    result = await automation._enrich_and_filter_item(item)

    assert result is None
    automation.tmdb_client.get_watch_providers.assert_awaited_once_with(1, "movie")


@pytest.mark.asyncio
async def test_filter_and_request_uses_local_content_for_downloaded_check():
    automation = TraktRecommendationsAutomation()
    automation.job_data = {"media_type": "movie"}
    automation.local_content = {"movie": {"27205"}}
    automation.db_manager = MagicMock()
    automation.db_manager.check_request_exists.return_value = False
    automation.db_manager.check_pending_request_exists.return_value = False
    automation.seer_client = MagicMock()
    automation.seer_client.check_already_downloaded = AsyncMock(return_value=True)
    automation.seer_client.check_already_requested = AsyncMock(return_value=False)
    automation.seer_client.request_media = AsyncMock(return_value=True)

    requested_count, dry_run_items = await automation.filter_and_request([
        {"id": 27205, "title": "Inception", "media_type": "movie"},
    ])

    assert requested_count == 0
    assert dry_run_items is None
    automation.seer_client.check_already_downloaded.assert_awaited_once_with(
        27205,
        "movie",
        automation.local_content,
    )
    automation.seer_client.check_already_requested.assert_not_awaited()
    automation.seer_client.request_media.assert_not_awaited()


@pytest.mark.asyncio
async def test_filter_and_request_passes_anime_flag_to_seer():
    automation = TraktRecommendationsAutomation()
    automation.job_data = {"media_type": "tv"}
    automation.local_content = {}
    automation.seer_discovered_ids = set()
    automation.db_manager = MagicMock()
    automation.db_manager.check_request_exists.return_value = False
    automation.db_manager.check_pending_request_exists.return_value = False
    automation.seer_client = MagicMock()
    automation.seer_client.check_already_downloaded = AsyncMock(return_value=False)
    automation.seer_client.check_already_requested = AsyncMock(return_value=False)
    automation.seer_client.request_media = AsyncMock(return_value=True)

    requested_count, dry_run_items = await automation.filter_and_request([
        {
            "id": 21,
            "title": "Anime Show",
            "media_type": "tv",
            "genre_ids": [16],
            "original_language": "ja",
            "origin_country": ["JP"],
        },
    ])

    assert requested_count == 1
    assert dry_run_items is None
    automation.seer_client.request_media.assert_awaited_once_with(
        "tv",
        {
            "id": 21,
            "title": "Anime Show",
            "media_type": "tv",
            "genre_ids": [16],
            "original_language": "ja",
            "origin_country": ["JP"],
        },
        source={"id": "trakt_recommendations"},
        user=None,
        is_anime=True,
    )


@pytest.mark.asyncio
async def test_initialize_components_skips_seer_cache_sync_in_dry_run():
    automation = TraktRecommendationsAutomation()
    automation.job_data = {"filters": {}, "media_type": "movie"}
    automation.env_vars = {
        "SEER_API_URL": "http://seer",
        "SEER_TOKEN": "token",
        "SEER_USER_NAME": "user",
        "SEER_USER_PSW": "pass",
        "SEER_SESSION_TOKEN": "session",
        "TMDB_API_KEY": "tmdb",
        "SELECTED_SERVICE": "jellyfin",
    }
    automation._load_existing_content = AsyncMock(return_value={})
    automation._build_trakt_client = MagicMock(return_value=MagicMock())

    with (
        patch("api_service.jobs._trakt_automation_base.SeerClient") as seer_cls,
        patch("api_service.jobs._trakt_automation_base.TMDbClient"),
    ):
        seer = seer_cls.return_value
        seer.init = AsyncMock()

        await automation._initialize_components(dry_run=True)

    seer.init.assert_not_awaited()


@pytest.mark.asyncio
async def test_filter_and_request_skips_seer_discovered_ids():
    automation = TraktRecommendationsAutomation()
    automation.job_data = {"media_type": "movie"}
    automation.local_content = {}
    automation.seer_discovered_ids = {"27205"}
    automation.db_manager = MagicMock()
    automation.db_manager.check_request_exists.return_value = False
    automation.seer_client = MagicMock()
    automation.seer_client.check_already_downloaded = AsyncMock(return_value=False)
    automation.seer_client.check_already_requested = AsyncMock(return_value=False)
    automation.seer_client.request_media = AsyncMock(return_value=True)

    requested_count, dry_run_items = await automation.filter_and_request([
        {"id": 27205, "title": "Inception", "media_type": "movie"},
    ])

    assert requested_count == 0
    assert dry_run_items is None
    automation.seer_client.check_already_downloaded.assert_not_awaited()
    automation.seer_client.check_already_requested.assert_not_awaited()
    automation.seer_client.request_media.assert_not_awaited()
