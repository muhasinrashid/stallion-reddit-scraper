"""Unified Reddit fetch facade — HTTP fast path with browser escalation."""

from __future__ import annotations

from typing import Any, AsyncIterator

from src.fetch_strategy import FetchStrategy
from src.log_utils import log_info, log_warning
from src.reddit_browser import RedditBrowserFetcher
from src.reddit_http import RedditHttpClient, parse_post_with_comments_payload


class RedditClient:
    """Route Reddit requests through HTTP/RSS first, then Playwright on hard failures."""

    def __init__(self, proxy_url: str | None = None) -> None:
        self._proxy_url = proxy_url
        self._http: RedditHttpClient | None = None
        self._browser_fetcher: RedditBrowserFetcher | None = None

    async def __aenter__(self) -> RedditClient:
        self._http = RedditHttpClient(proxy_url=self._proxy_url)
        await self._http.__aenter__()
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._browser_fetcher:
            await self._browser_fetcher.close()
            self._browser_fetcher = None
        if self._http:
            await self._http.__aexit__(*args)
            self._http = None

    async def _get_browser(self) -> RedditBrowserFetcher:
        if not self._browser_fetcher:
            self._browser_fetcher = RedditBrowserFetcher(proxy_url=self._proxy_url)
            await self._browser_fetcher.__aenter__()
        return self._browser_fetcher

    def _require_http(self) -> RedditHttpClient:
        if not self._http:
            raise RuntimeError("RedditClient is not initialized")
        return self._http

    async def fetch_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | list[Any] | None:
        http = self._require_http()
        payload = await http.fetch_json(path, params)
        if payload is not None:
            log_info("fetch_json strategy=%s path=%s", FetchStrategy.HTTP_JSON.value, path)
            return payload

        log_warning("HTTP JSON unavailable for %s — escalating to browser", path)
        browser = await self._get_browser()
        payload = await browser.fetch_json(path, params)
        if payload is not None:
            log_info("fetch_json strategy=%s path=%s", FetchStrategy.BROWSER_JSON.value, path)
        return payload

    async def paginate_listing(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        after: str | None = None,
        max_items: int = 100,
        deadline: float | None = None,
        kinds: frozenset[str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield listing posts via the HTTP/RSS fast path."""
        http = self._require_http()
        log_info("paginate_listing path=%s max_items=%d", path, max_items)
        async for post in http.paginate_listing(
            path,
            params=params,
            after=after,
            max_items=max_items,
            deadline=deadline,
            kinds=kinds,
        ):
            yield post

    def _needs_browser_for_comments(
        self,
        post_data: dict[str, Any] | None,
        comments: list[dict[str, Any]],
        *,
        max_comments: int,
    ) -> bool:
        if max_comments <= 0:
            return False
        if post_data is None:
            return True
        if comments:
            return False
        # Always try browser when comments were requested but HTTP returned none.
        return True

    async def fetch_post_with_comments(
        self,
        permalink: str,
        *,
        max_comments: int = 100,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """Fetch post detail and comments; browser fallback when HTTP JSON is blocked or comments missing."""
        http = self._require_http()
        path = permalink.rstrip("/")
        if not path.startswith("/"):
            path = f"/{path}"

        post_data, comments = await http.fetch_post_with_comments(permalink, max_comments=max_comments)

        if post_data is not None and not self._needs_browser_for_comments(post_data, comments, max_comments=max_comments):
            post_data["_data_source"] = FetchStrategy.HTTP_JSON.value
            log_info(
                "fetch_post_with_comments strategy=%s post_id=%s comments=%d",
                FetchStrategy.HTTP_JSON.value,
                post_data.get("id"),
                len(comments),
            )
            return post_data, comments

        if post_data is not None:
            log_warning(
                "HTTP returned post %s with %d/%d comments — escalating to browser",
                post_data.get("id"),
                len(comments),
                int(post_data.get("num_comments") or 0),
            )
        else:
            log_warning("HTTP post fetch failed for %s — escalating to browser", path)

        browser = await self._get_browser()
        payload = await browser.fetch_json(path, {"limit": min(max_comments, 100)})
        browser_post, browser_comments = parse_post_with_comments_payload(payload, max_comments=max_comments)

        if browser_post is not None:
            browser_post["_data_source"] = FetchStrategy.BROWSER_JSON.value
            log_info(
                "fetch_post_with_comments strategy=%s post_id=%s comments=%d",
                FetchStrategy.BROWSER_JSON.value,
                browser_post.get("id"),
                len(browser_comments),
            )
            return browser_post, browser_comments

        if post_data is not None:
            post_data["_data_source"] = FetchStrategy.HTTP_JSON.value
            log_warning(
                "Browser fallback failed for %s — keeping HTTP post without comments",
                post_data.get("id"),
            )
            return post_data, comments

        return None, []
