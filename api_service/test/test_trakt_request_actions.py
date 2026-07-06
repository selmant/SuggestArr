from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api_service.services.trakt import request_actions


class FakeTraktClient:
    instances = []

    def __init__(
        self,
        client_id,
        client_secret,
        access_token="",
        refresh_token="",
        expires_at=None,
        session=None,
        db=None,
        link_id=None,
        token_source="manual_oauth",
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self.db = db
        self.link_id = link_id
        self.token_source = token_source
        self.add_to_history = AsyncMock(return_value={"added": {"movies": 1}})
        self.remove_from_history = AsyncMock(return_value={"deleted": {"movies": 1}})
        self.add_rating = AsyncMock(return_value={"added": {"movies": 1}})
        self.remove_rating = AsyncMock(return_value={"deleted": {"movies": 1}})
        self.get_item_sync_status = AsyncMock(return_value={"watched": False, "rating": None})
        FakeTraktClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def linked_db():
    db = MagicMock()
    db.get_media_user_identity.return_value = {
        "id": 7,
        "provider": "jellyfin",
        "external_user_id": "jf-1",
        "external_username": "Alice",
    }
    db.get_trakt_account_link.return_value = {
        "id": 9,
        "media_user_identity_id": 7,
        "connected": True,
        "token_source": "manual_oauth",
    }
    db.get_trakt_oauth_tokens.return_value = {
        "access_token": "access",
        "refresh_token": "refresh",
        "expires_at": 12345,
    }
    return db


@pytest.mark.asyncio
async def test_mark_request_watched_resolves_request_user_and_posts_history():
    db = linked_db()
    FakeTraktClient.instances = []

    with patch.object(request_actions, "TraktClient", FakeTraktClient), \
            patch.object(request_actions, "load_env_vars", return_value={
                "SELECTED_SERVICE": "jellyfin",
                "TRAKT_CLIENT_ID": "cid",
                "TRAKT_CLIENT_SECRET": "secret",
            }):
        result = await request_actions.mark_request_watched(
            db, "550", "movie", "jf-1", watched_at="now", rating_stars=4.5,
        )

    assert result["watched"] is True
    assert result["rating"] == 9
    db.get_media_user_identity.assert_called_once_with("jellyfin", "jf-1")
    client = FakeTraktClient.instances[0]
    client.add_to_history.assert_awaited_once()
    assert client.add_to_history.await_args.args[0:2] == ("movie", "550")
    client.add_rating.assert_awaited_once_with("movie", "550", 9)


@pytest.mark.asyncio
async def test_get_request_trakt_status_requires_linked_trakt_account():
    db = linked_db()
    db.get_trakt_account_link.return_value = None

    with patch.object(request_actions, "load_env_vars", return_value={
        "SELECTED_SERVICE": "jellyfin",
        "TRAKT_CLIENT_ID": "cid",
        "TRAKT_CLIENT_SECRET": "secret",
    }):
        with pytest.raises(ValueError, match="Trakt account not linked"):
            await request_actions.get_request_trakt_status(db, "550", "movie", "jf-1")
