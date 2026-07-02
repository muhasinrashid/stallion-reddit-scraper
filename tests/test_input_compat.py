"""Tests for input_compat alias normalization."""

from __future__ import annotations

from src.input_compat import RunConfig


def test_legacy_fields_map_to_run_config():
    config = RunConfig.from_actor_input(
        {
            "startUrls": [{"url": "https://www.reddit.com/r/python/new/"}],
            "searches": ["dashcam"],
            "searchCommunityName": "cars",
            "maxItems": 50,
            "maxComments": 5,
            "postDateLimit": "2024-01-01",
            "proxy": {"useApifyProxy": True},
        }
    )
    assert config.start_urls == ["https://www.reddit.com/r/python/new/"]
    assert config.searches == ["dashcam"]
    assert config.search_community == "cars"
    assert config.max_items == 50
    assert config.max_comments == 5
    assert config.posted_after == "2024-01-01"
    assert config.crawl_comments is True


def test_harshmaur_aliases_map_to_run_config():
    config = RunConfig.from_actor_input(
        {
            "searchTerms": ["ev charging"],
            "withinCommunity": "r/electricvehicles",
            "maxPostsCount": 200,
            "maxCommentsPerPost": 10,
            "postedAfter": "2025-06-01",
            "postedBefore": "2025-06-30",
            "subredditUrls": [{"url": "https://www.reddit.com/r/cartalkuk/new/"}],
            "searchComments": True,
            "fastMode": False,
            "onlyWithFlair": "Question",
        }
    )
    assert config.searches == ["ev charging"]
    assert config.search_community == "electricvehicles"
    assert config.max_items == 200
    assert config.max_comments == 10
    assert config.crawl_comments is True
    assert config.posted_before == "2025-06-30"
    assert "https://www.reddit.com/r/cartalkuk/new/" in config.start_urls
    assert config.search_comments is True
    assert config.fast_mode is False
    assert config.only_with_flair == "Question"


def test_crawl_comments_stays_on_when_apify_sends_false_default_with_max_comments():
    config = RunConfig.from_actor_input(
        {
            "maxComments": 10,
            "crawlCommentsPerPost": False,
        }
    )
    assert config.max_comments == 10
    assert config.crawl_comments is True
    assert config.needs_full_post_fetch() is True


def test_crawl_comments_auto_when_field_omitted():
    config = RunConfig.from_actor_input({"maxComments": 10})
    assert config.crawl_comments is True
    assert config.needs_full_post_fetch() is True


def test_as_mode_input_exposes_legacy_keys():
    config = RunConfig.from_actor_input({"searchTerms": ["python"], "maxPostsCount": 25})
    mode_input = config.as_mode_input()
    assert mode_input["searches"] == ["python"]
    assert mode_input["searchTerms"] == ["python"]
    assert mode_input["maxItems"] == 25
    assert mode_input["maxPostsCount"] == 25
