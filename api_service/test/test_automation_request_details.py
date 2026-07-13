"""Tests for automation request details route."""

import unittest
from unittest.mock import AsyncMock, patch

from flask import Flask, g

from api_service.auth.limiter import limiter
from api_service.blueprints.automation.routes import automation_bp


class TestAutomationRequestDetailsRoute(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.config["TESTING"] = True
        app.config["RATELIMIT_ENABLED"] = False
        limiter.init_app(app)
        app.register_blueprint(automation_bp, url_prefix="/api/automation")

        @app.before_request
        def _inject_admin():
            g.current_user = {"id": 1, "role": "admin", "username": "admin"}

        self.client = app.test_client()

    def test_returns_details_payload(self):
        payload = {
            "available": True,
            "tmdb_id": "123",
            "media_type": "movie",
            "title": "Example",
            "genres": ["Drama"],
            "cast": [],
        }

        with patch(
            "api_service.blueprints.automation.routes.get_request_details",
            new=AsyncMock(return_value=payload),
        ) as get_request_details:
            resp = self.client.get("/api/automation/requests/123/movie/details")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), payload)
        get_request_details.assert_awaited_once()

    def test_returns_400_for_invalid_media_type(self):
        resp = self.client.get("/api/automation/requests/123/anime/details")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("movie or tv", resp.get_json()["message"])

    def test_returns_502_when_seer_is_not_configured(self):
        with patch(
            "api_service.blueprints.automation.routes.get_request_details",
            new=AsyncMock(side_effect=RuntimeError("Seer API URL and token are not configured")),
        ):
            resp = self.client.get("/api/automation/requests/123/movie/details")

        self.assertEqual(resp.status_code, 502)
        self.assertIn("not configured", resp.get_json()["message"])

    def test_collection_request_route_enqueues(self):
        payload = {"enqueued": True, "tmdb_id": "552", "media_type": "movie"}
        with patch(
            "api_service.blueprints.automation.routes.request_collection_part",
            new=AsyncMock(return_value=payload),
        ) as request_fn:
            resp = self.client.post(
                "/api/automation/requests/collection/request",
                json={
                    "tmdb_id": 552,
                    "media_type": "movie",
                    "mirror_tmdb_id": 550,
                    "mirror_media_type": "movie",
                    "metadata": {"title": "Fight Club 3"},
                    "collection_name": "Fight Club Collection",
                },
            )

        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.get_json(), payload)
        request_fn.assert_awaited_once()

    def test_collection_request_route_requires_ids(self):
        resp = self.client.post(
            "/api/automation/requests/collection/request",
            json={"media_type": "movie"},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("required", resp.get_json()["message"])


if __name__ == "__main__":
    unittest.main()
