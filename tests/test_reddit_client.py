"""Tests for RedditClient browser escalation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.fetch_strategy import FetchStrategy
from src.reddit_client import RedditClient

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.asyncio
async def test_fetch_post_with_comments_uses_http_when_available():
    post_data = {"id": "abc123", "title": "test", "num_comments": 2}
    comments = [{"id": "c1", "body": "hi", "created_utc": 1.0, "author": "u"}]

    async with RedditClient() as client:
        with patch.object(
            client._require_http(),
            "fetch_post_with_comments",
            new=AsyncMock(return_value=(post_data, comments)),
        ):
            post, comments = await client.fetch_post_with_comments(
                "/r/dashcam/comments/abc123/x/",
                max_comments=10,
            )
            assert post is not None
            assert post["_data_source"] == FetchStrategy.HTTP_JSON.value


@pytest.mark.asyncio
async def test_fetch_post_with_comments_escalates_when_http_returns_empty_comments():
    payload = json.loads((FIXTURES / "post_with_comments.json").read_text())
    post_data = payload[0]["data"]["children"][0]["data"]
    post_data["num_comments"] = 0

    async with RedditClient() as client:
        with patch.object(
            client._require_http(),
            "fetch_post_with_comments",
            new=AsyncMock(return_value=(post_data, [])),
        ):
            browser = AsyncMock()
            browser.fetch_json = AsyncMock(return_value=payload)
            with patch.object(client, "_get_browser", new=AsyncMock(return_value=browser)):
                post, comments = await client.fetch_post_with_comments(
                    "/r/dashcam/comments/abc123/x/",
                    max_comments=10,
                )
                assert post is not None
                assert post["_data_source"] == FetchStrategy.BROWSER_JSON.value
                assert len(comments) == 2
                browser.fetch_json.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_post_with_comments_escalates_to_browser_on_http_failure():
    payload = json.loads((FIXTURES / "post_with_comments.json").read_text())
    post_data = payload[0]["data"]["children"][0]["data"]

    async with RedditClient() as client:
        with patch.object(
            client._require_http(),
            "fetch_post_with_comments",
            new=AsyncMock(return_value=(None, [])),
        ):
            browser = AsyncMock()
            browser.fetch_json = AsyncMock(return_value=payload)
            with patch.object(client, "_get_browser", new=AsyncMock(return_value=browser)):
                post, comments = await client.fetch_post_with_comments(
                    "/r/dashcam/comments/abc123/x/",
                    max_comments=10,
                )
                assert post is not None
                assert post["id"] == post_data["id"]
                assert post["_data_source"] == FetchStrategy.BROWSER_JSON.value
                assert len(comments) == 2
