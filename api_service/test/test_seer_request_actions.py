from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from api_service.services.seer import request_actions


class FakeSeerClient:
    instances = []
    decline_should_fail = False
    media_details_response = None

    def __init__(self, api_url, api_key, session_token=None, **kwargs):
        self.api_url = api_url
        self.api_key = api_key
        self.session_token = session_token
        self.index = {}
        self.approve_request = AsyncMock(return_value=True)
        self.decline_request = AsyncMock(side_effect=self._decline_side_effect)
        self.get_media_details = AsyncMock(side_effect=self._get_media_details_side_effect)
        FakeSeerClient.instances.append(self)

    async def _get_media_details_side_effect(self, tmdb_id, media_type):
        return FakeSeerClient.media_details_response

    async def _decline_side_effect(self, request_id):
        if FakeSeerClient.decline_should_fail:
            return False
        return True

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get_requests_index(self):
        return self.index


def _configured_env():
    return {
        "SEER_API_URL": "http://seer.local",
        "SEER_TOKEN": "token",
        "integrations": {
            "seer": {
                "api_url": "http://seer.local",
                "api_key": "token",
            },
        },
    }


@pytest.mark.asyncio
async def test_get_request_details_returns_unavailable_when_seer_has_no_payload():
    db = MagicMock()
    FakeSeerClient.instances = []
    FakeSeerClient.media_details_response = None

    with patch.object(request_actions, "SeerClient", FakeSeerClient), \
            patch.object(request_actions, "load_env_vars", return_value=_configured_env()):
        result = await request_actions.get_request_details(db, "999", "movie")

    assert result["available"] is False
    assert result["tmdb_id"] == "999"
    assert result["media_type"] == "movie"


@pytest.mark.asyncio
async def test_get_request_details_returns_formatted_payload():
    db = MagicMock()
    FakeSeerClient.instances = []
    FakeSeerClient.media_details_response = {
        "available": True,
        "tmdb_id": "123",
        "media_type": "movie",
        "title": "Example",
        "genres": ["Drama"],
        "cast": [],
    }
    request_actions.invalidate_request_details_cache()

    with patch.object(request_actions, "SeerClient", FakeSeerClient), \
            patch.object(request_actions, "load_env_vars", return_value=_configured_env()):
        result = await request_actions.get_request_details(db, "123", "movie")

    assert result["available"] is True
    assert result["title"] == "Example"
    assert result["genres"] == ["Drama"]
    assert len(FakeSeerClient.instances) == 1
    assert FakeSeerClient.instances[0].get_media_details.await_count == 1

    with patch.object(request_actions, "SeerClient", FakeSeerClient), \
            patch.object(request_actions, "load_env_vars", return_value=_configured_env()):
        cached = await request_actions.get_request_details(db, "123", "movie")

    assert cached == result
    assert FakeSeerClient.instances[0].get_media_details.await_count == 1


@pytest.mark.asyncio
async def test_get_request_details_cache_expires(monkeypatch):
    db = MagicMock()
    FakeSeerClient.instances = []
    FakeSeerClient.media_details_response = {
        "available": True,
        "tmdb_id": "123",
        "media_type": "movie",
        "title": "Example",
    }
    request_actions.invalidate_request_details_cache()
    now = {"value": 1000.0}
    monkeypatch.setattr(request_actions.time, "monotonic", lambda: now["value"])

    with patch.object(request_actions, "SeerClient", FakeSeerClient), \
            patch.object(request_actions, "load_env_vars", return_value=_configured_env()):
        first = await request_actions.get_request_details(db, "123", "movie")
        now["value"] += request_actions._DETAILS_CACHE_TTL_SECONDS - 1
        cached = await request_actions.get_request_details(db, "123", "movie")
        now["value"] += 2
        refreshed = await request_actions.get_request_details(db, "123", "movie")

    assert first == cached
    assert refreshed == first
    total_fetches = sum(
        client.get_media_details.await_count
        for client in FakeSeerClient.instances
    )
    assert total_fetches == 2


@pytest.mark.asyncio
async def test_get_request_seer_status_returns_pending_payload():
    db = MagicMock()
    FakeSeerClient.instances = []
    client = FakeSeerClient("http://seer.local", "token")
    client.index = {
        ("movie", "123"): [{"id": 9, "status": 1, "media_status": 2}],
    }

    with patch.object(request_actions, "SeerClient", FakeSeerClient), \
            patch.object(request_actions, "load_env_vars", return_value=_configured_env()), \
            patch.object(request_actions, "_get_requests_index", AsyncMock(return_value=client.index)):
        result = await request_actions.get_request_seer_status(db, "123", "movie")

    assert result["seer_status"] == "pending"
    assert result["can_action"] is True
    assert result["seer_request_ids"] == [9]
    db.update_request_seer_state.assert_called_once()


@pytest.mark.asyncio
async def test_get_request_seer_status_returns_not_found_when_missing():
    db = MagicMock()

    with patch.object(request_actions, "SeerClient", FakeSeerClient), \
            patch.object(request_actions, "load_env_vars", return_value=_configured_env()), \
            patch.object(request_actions, "_get_requests_index", AsyncMock(return_value={})):
        result = await request_actions.get_request_seer_status(db, "999", "tv")

    assert result["seer_status"] == "not_found"
    assert result["can_action"] is False
    assert result["seer_request_ids"] == []
    db.update_request_seer_state.assert_called_once_with(
        "999",
        "tv",
        seer_request_id=None,
        seer_request_status=None,
        seer_media_status=None,
        seer_status="not_found",
        seer_updated_at=ANY,
    )


@pytest.mark.asyncio
async def test_get_request_seer_statuses_batch_maps_many_items():
    db = MagicMock()
    index = {
        ("movie", "1"): [{"id": 1, "status": 2, "media_status": 5}],
        ("tv", "2"): [{"id": 2, "status": 1, "media_status": 2}],
    }

    with patch.object(request_actions, "SeerClient", FakeSeerClient), \
            patch.object(request_actions, "load_env_vars", return_value=_configured_env()), \
            patch.object(request_actions, "_get_requests_index", AsyncMock(return_value=index)):
        result = await request_actions.get_request_seer_statuses_batch(
            db,
            [
                {"tmdb_id": "1", "media_type": "movie"},
                {"request_id": "2", "media_type": "tv"},
            ],
        )

    assert len(result["statuses"]) == 2
    assert result["statuses"][0]["seer_status"] == "available"
    assert result["statuses"][1]["seer_status"] == "pending"
    assert db.update_request_seer_state.call_count == 2


@pytest.mark.asyncio
async def test_approve_request_acts_on_all_pending_matches():
    db = MagicMock()
    FakeSeerClient.instances = []
    FakeSeerClient.decline_should_fail = False
    index_state = {
        ("tv", "55"): [
            {"id": 10, "status": 1, "media_status": 2},
            {"id": 11, "status": 1, "media_status": 2},
        ],
    }
    call_count = {"force": 0}

    async def refresh_index(client, *, force=False):
        if force:
            call_count["force"] += 1
            if call_count["force"] >= 2:
                index_state[("tv", "55")] = [
                    {"id": 10, "status": 2, "media_status": 3},
                    {"id": 11, "status": 2, "media_status": 3},
                ]
        return index_state

    with patch.object(request_actions, "SeerClient", FakeSeerClient), \
            patch.object(request_actions, "load_env_vars", return_value=_configured_env()), \
            patch.object(request_actions, "_get_requests_index", side_effect=refresh_index):
        result = await request_actions.approve_request(db, "55", "tv")

    active_client = FakeSeerClient.instances[-1]
    assert active_client.approve_request.await_count == 2
    active_client.approve_request.assert_any_await(10)
    active_client.approve_request.assert_any_await(11)
    assert result["seer_status"] == "processing"
    assert result["can_action"] is False


@pytest.mark.asyncio
async def test_decline_request_raises_when_seer_call_fails():
    db = MagicMock()
    FakeSeerClient.instances = []
    FakeSeerClient.decline_should_fail = True
    index = {
        ("movie", "7"): [{"id": 3, "status": 1, "media_status": 2}],
    }

    with patch.object(request_actions, "SeerClient", FakeSeerClient), \
            patch.object(request_actions, "load_env_vars", return_value=_configured_env()), \
            patch.object(request_actions, "_get_requests_index", AsyncMock(return_value=index)):
        with pytest.raises(RuntimeError, match="could not decline"):
            await request_actions.decline_request(db, "7", "movie")

    db.update_request_seer_state.assert_not_called()


@pytest.mark.asyncio
async def test_decline_request_persists_seer_state_to_db():
    db = MagicMock()
    FakeSeerClient.instances = []
    FakeSeerClient.decline_should_fail = False
    index_state = {
        ("movie", "7"): [{"id": 3, "status": 1, "media_status": 2}],
    }
    call_count = {"force": 0}

    async def refresh_index(client, *, force=False):
        if force:
            call_count["force"] += 1
            if call_count["force"] >= 2:
                index_state[("movie", "7")] = [
                    {"id": 3, "status": 3, "media_status": 2, "updated_at": "2026-01-01T00:00:00Z"},
                ]
        return index_state

    with patch.object(request_actions, "SeerClient", FakeSeerClient), \
            patch.object(request_actions, "load_env_vars", return_value=_configured_env()), \
            patch.object(request_actions, "_get_requests_index", side_effect=refresh_index):
        result = await request_actions.decline_request(db, "7", "movie")

    assert result["seer_status"] == "declined"
    db.update_request_seer_state.assert_called_once_with(
        "7",
        "movie",
        seer_request_id=3,
        seer_request_status=3,
        seer_media_status=2,
        seer_status="declined",
        seer_updated_at="2026-01-01 00:00:00",
    )


@pytest.mark.asyncio
async def test_decline_request_persists_when_no_pending_requests_remain():
    db = MagicMock()
    FakeSeerClient.instances = []
    FakeSeerClient.decline_should_fail = False
    index = {
        ("movie", "7"): [{"id": 3, "status": 3, "media_status": 2, "updated_at": "2026-01-01T00:00:00Z"}],
    }

    with patch.object(request_actions, "SeerClient", FakeSeerClient), \
            patch.object(request_actions, "load_env_vars", return_value=_configured_env()), \
            patch.object(request_actions, "_get_requests_index", AsyncMock(return_value=index)):
        result = await request_actions.decline_request(db, "7", "movie")

    assert result["seer_status"] == "declined"
    db.update_request_seer_state.assert_called_once_with(
        "7",
        "movie",
        seer_request_id=3,
        seer_request_status=3,
        seer_media_status=2,
        seer_status="declined",
        seer_updated_at="2026-01-01 00:00:00",
    )


@pytest.mark.asyncio
async def test_decline_request_keeps_declined_state_when_seer_is_eventually_consistent():
    db = MagicMock()
    FakeSeerClient.instances = []
    FakeSeerClient.decline_should_fail = False
    pending = {("movie", "7"): [{"id": 3, "status": 1, "media_status": 2}]}

    with patch.object(request_actions, "SeerClient", FakeSeerClient), \
            patch.object(request_actions, "load_env_vars", return_value=_configured_env()), \
            patch.object(request_actions, "_get_requests_index", AsyncMock(return_value=pending)):
        result = await request_actions.decline_request(db, "7", "movie")

    assert result["seer_status"] == "declined"
    db.update_request_seer_state.assert_called_once_with(
        "7",
        "movie",
        seer_request_id=3,
        seer_request_status=3,
        seer_media_status=2,
        seer_status="declined",
        seer_updated_at=ANY,
    )


def test_derive_seer_status_maps_media_states():
    from api_service.services.seer import seer_status

    assert seer_status.derive_seer_status(1, 2) == "pending"
    assert seer_status.derive_seer_status(3, 2) == "declined"
    assert seer_status.derive_seer_status(2, 5) == "available"
    assert seer_status.derive_seer_status(2, 4) == "partially_available"
    assert seer_status.derive_seer_status(2, 3) == "processing"
    assert seer_status.derive_seer_status(2, 2) == "unavailable"


@pytest.mark.asyncio
async def test_request_collection_part_mirrors_source_user_and_settings():
    db = MagicMock()
    db.get_request_mirror_context.return_value = {
        "user_id": "u1",
        "user_name": "Alice",
        "is_anime": True,
        "source_id": "900",
        "source_origin": "jellyfin",
    }
    db.check_request_exists.return_value = False
    FakeSeerClient.instances = []

    class RequestingFakeSeerClient(FakeSeerClient):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.anime_profile_config = kwargs.get("anime_profile_config") or {}
            self.request_media = AsyncMock(return_value=True)

    env = _configured_env()
    env["SEER_ANIME_PROFILE_CONFIG"] = {
        "anime_movie": {"serverId": 1, "profileId": 2, "rootFolder": "/anime"},
    }
    env["FILTER_NUM_SEASONS"] = "all"
    env["REQUEST_FIRST_SEASON_ONLY"] = False

    with patch.object(request_actions, "SeerClient", RequestingFakeSeerClient), \
            patch.object(request_actions, "load_env_vars", return_value=env):
        result = await request_actions.request_collection_part(
            db,
            tmdb_id="552",
            media_type="movie",
            mirror_tmdb_id="550",
            mirror_media_type="movie",
            metadata={
                "title": "Fight Club 3",
                "overview": "More soap.",
                "poster_path": "/fight3.jpg",
                "release_date": "2027-01-01",
            },
            collection_name="Fight Club Collection",
        )

    assert result["enqueued"] is True
    assert result["tmdb_id"] == "552"
    assert result["media_type"] == "movie"
    db.get_request_mirror_context.assert_called_once_with("movie", "550")
    client = FakeSeerClient.instances[-1]
    assert client.anime_profile_config["anime_movie"]["profileId"] == 2
    client.request_media.assert_awaited_once()
    kwargs = client.request_media.await_args.kwargs
    assert kwargs["media_type"] == "movie"
    assert kwargs["media"]["id"] == 552
    assert kwargs["media"]["title"] == "Fight Club 3"
    assert kwargs["user"] == {"id": "u1", "name": "Alice"}
    assert kwargs["is_anime"] is True
    assert kwargs["source"]["id"] == "900"
    assert kwargs["source"]["_source_origin"] == "jellyfin"
    assert "Fight Club Collection" in kwargs["rationale"]


@pytest.mark.asyncio
async def test_request_collection_part_rejects_non_movie():
    db = MagicMock()
    with pytest.raises(ValueError, match="movie"):
        await request_actions.request_collection_part(
            db,
            tmdb_id="1",
            media_type="tv",
            mirror_tmdb_id="2",
            mirror_media_type="movie",
        )


@pytest.mark.asyncio
async def test_request_collection_part_errors_when_mirror_missing():
    db = MagicMock()
    db.get_request_mirror_context.return_value = None

    with pytest.raises(ValueError, match="mirror"):
        await request_actions.request_collection_part(
            db,
            tmdb_id="552",
            media_type="movie",
            mirror_tmdb_id="550",
            mirror_media_type="movie",
        )
