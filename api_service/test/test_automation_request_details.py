"""Tests for automation request details route."""

import unittest
from unittest.mock import AsyncMock, patch

from flask import Flask

from api_service.auth.limiter import limiter
from api_service.blueprints.automation.routes import automation_bp


class TestAutomationRequestDetailsRoute(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.config["TESTING"] = True
        app.config["RATELIMIT_ENABLED"] = False
        limiter.init_app(app)
        app.register_blueprint(automation_bp, url_prefix="/api/automation")
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


if __name__ == "__main__":
    unittest.main()
