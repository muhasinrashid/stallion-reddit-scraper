"""Tests for reddit_http pagination with mocked responses."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.reddit_http import RedditHttpClient

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.asyncio
async def test_paginate_listing_yields_posts():
    listing = json.loads((FIXTURES / "listing_post.json").read_text())

    async with RedditHttpClient() as client:
        with patch.object(client, "fetch_json", new=AsyncMock(return_value=listing)):
            posts = []
            async for post in client.paginate_listing("/r/dashcam/new", max_items=5):
                posts.append(post)
            assert len(posts) == 1
            assert posts[0]["id"] == "abc123"


@pytest.mark.asyncio
async def test_fetch_post_with_comments():
    payload = json.loads((FIXTURES / "post_with_comments.json").read_text())

    async with RedditHttpClient() as client:
        with patch.object(client, "fetch_json", new=AsyncMock(return_value=payload)):
            post, comments = await client.fetch_post_with_comments(
                "/r/dashcam/comments/abc123/x/",
                max_comments=10,
            )
            assert post is not None
            assert post["id"] == "abc123"
            assert len(comments) == 2
            assert comments[0]["body"] == "Great post!"
