"""Tests for Playwright Reddit fallback circuit breaker."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.reddit_browser import BROWSER_BLOCK_CIRCUIT_LIMIT, RedditBrowserFetcher


def _blocked_response(status: int = 403) -> MagicMock:
    response = MagicMock()
    response.status = status
    response.text = AsyncMock(return_value="")
    return response


@pytest.mark.asyncio
async def test_browser_disables_after_consecutive_403s():
    fetcher = RedditBrowserFetcher()
    page = AsyncMock()
    page.goto = AsyncMock(return_value=_blocked_response(403))
    page.close = AsyncMock()

    context = AsyncMock()
    context.new_page = AsyncMock(return_value=page)

    with patch.object(fetcher, "_ensure_context", new=AsyncMock(return_value=context)):
        for _ in range(BROWSER_BLOCK_CIRCUIT_LIMIT):
            result = await fetcher.fetch_json("/r/dashcam/comments/abc/x")
            assert result is None

        assert fetcher._disabled is True

        page.goto.reset_mock()
        result = await fetcher.fetch_json("/r/dashcam/comments/def/y")
        assert result is None
        page.goto.assert_not_awaited()


@pytest.mark.asyncio
async def test_browser_success_resets_block_counter():
    fetcher = RedditBrowserFetcher()
    page = AsyncMock()
    page.close = AsyncMock()

    blocked = _blocked_response(403)
    ok = MagicMock()
    ok.status = 200
    ok.text = AsyncMock(return_value='{"ok": true}')

    # First call: both bases 403 → one block. Second call: success.
    page.goto = AsyncMock(side_effect=[blocked, blocked, ok])

    context = AsyncMock()
    context.new_page = AsyncMock(return_value=page)

    with patch.object(fetcher, "_ensure_context", new=AsyncMock(return_value=context)):
        assert await fetcher.fetch_json("/r/dashcam/comments/a/x") is None
        assert fetcher._consecutive_blocks == 1
        assert await fetcher.fetch_json("/r/dashcam/comments/b/y") == {"ok": True}
        assert fetcher._consecutive_blocks == 0
        assert fetcher._disabled is False
