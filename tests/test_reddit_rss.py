"""Tests for RSS fallback parser."""

from pathlib import Path

from src.normalize import normalize_post
from src.reddit_rss import parse_rss_feed

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_rss_feed():
    xml = (FIXTURES / "listing_rss.xml").read_text()
    posts, after = parse_rss_feed(xml, subreddit="cartalkuk")
    assert len(posts) == 1
    assert posts[0]["id"] == "abc123"
    assert posts[0]["title"] == "Test post title"
    assert posts[0]["author"] == "tester"
    assert posts[0]["subreddit"] == "cartalkuk"
    assert after == "t3_abc123"


def test_normalize_rss_post():
    xml = (FIXTURES / "listing_rss.xml").read_text()
    posts, _ = parse_rss_feed(xml, subreddit="cartalkuk")
    row = normalize_post(posts[0])
    assert row["parsedId"] == "abc123"
    assert row["dataSource"] == "rss"
    assert row["username"] == "tester"
    assert row["upVotes"] == 0
