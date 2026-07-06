"""Tests for anime routing detection."""

from api_service.services.tmdb.anime_detection import is_anime_media


def test_detects_japanese_animation_as_anime():
    item = {
        "genre_ids": [16, 10759],
        "original_language": "ja",
        "origin_country": ["JP"],
    }

    assert is_anime_media(item) is True


def test_does_not_treat_non_japanese_animation_as_anime():
    item = {
        "genre_ids": [16, 35],
        "original_language": "en",
        "origin_country": ["US"],
    }

    assert is_anime_media(item) is False


def test_detects_anime_keyword_metadata():
    item = {
        "genre_ids": [18],
        "original_language": "en",
        "keywords": [{"name": "anime"}],
    }

    assert is_anime_media(item) is True
