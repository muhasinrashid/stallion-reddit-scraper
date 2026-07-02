"""Tests for normalize.py — mirrors ApifyRedditProvider field mapping."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.normalize import normalize_comment, normalize_post, parse_date_limit, passes_date_limit
from src.url_utils import parse_reddit_url

FIXTURES = Path(__file__).parent / "fixtures"


def test_post_from_apify_row_maps_fields():
    """Same assertions as consumer test_post_from_apify_row_maps_fields."""
    row = normalize_post(
        {
            "id": "abc123",
            "name": "t3_abc123",
            "title": "dashcam reliability",
            "selftext": "my dashcam overheated",
            "subreddit": "dashcam",
            "author": "tester",
            "score": 42,
            "num_comments": 7,
            "created_utc": datetime(2025, 8, 1, 12, 0, tzinfo=UTC).timestamp(),
            "permalink": "/r/dashcam/comments/abc123/x/",
        }
    )
    assert row["dataType"] == "post"
    assert row["parsedId"] == "abc123"
    assert row["parsedCommunityName"] == "dashcam"
    assert row["upVotes"] == 42
    assert row["numberOfComments"] == 7
    assert row["createdAt"] == "2025-08-01T12:00:00.000Z"
    assert row["url"] == "https://www.reddit.com/r/dashcam/comments/abc123/x/"


def test_normalize_from_listing_fixture():
    listing = json.loads((FIXTURES / "listing_post.json").read_text())
    child = listing["data"]["children"][0]["data"]
    row = normalize_post(child)
    assert row["parsedId"] == "abc123"
    assert row["title"] == "dashcam reliability"
    assert row["body"] == "my dashcam overheated"
    assert row["parsedCommunityName"] == "dashcam"
    assert row["communityName"] == "r/dashcam"
    assert row["username"] == "tester"


def test_removed_comments_dropped():
    raw = {"id": "x", "body": "[removed]", "author": "a", "score": 0, "created_utc": 0}
    assert normalize_comment(raw) is None


def test_post_date_limit_filter():
    min_ts = parse_date_limit("2025-01-01")
    assert passes_date_limit({"created_utc": datetime(2025, 6, 1, tzinfo=UTC).timestamp()}, min_ts)
    assert not passes_date_limit({"created_utc": datetime(2024, 6, 1, tzinfo=UTC).timestamp()}, min_ts)


def test_parse_listing_url():
    parsed = parse_reddit_url("https://www.reddit.com/r/cartalkuk/new/?include_over_18=on")
    assert parsed.kind == "listing"
    assert parsed.subreddit.lower() == "cartalkuk"
    assert parsed.sort == "new"
    assert parsed.include_nsfw is True


def test_parse_post_url():
    parsed = parse_reddit_url("https://www.reddit.com/r/CarTalkUK/comments/1uiuv92/new_car_under_10k/")
    assert parsed.kind == "post"
    assert parsed.post_id == "1uiuv92"


def test_parse_resume_after_url():
    parsed = parse_reddit_url("https://www.reddit.com/r/dashcam/new/?after=t3_abc123")
    assert parsed.after == "t3_abc123"


def test_bare_id_strips_prefix():
    row = normalize_post({"id": "t3_abc123", "name": "t3_abc123", "subreddit": "x", "title": "t"})
    assert row["parsedId"] == "abc123"
    assert row["id"] == "t3_abc123"
