"""HTTP client for Reddit — JSON API with RSS and session-cookie fallbacks."""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator
from urllib.parse import urlencode

import httpx

from src.log_utils import log_info, log_warning
from src.reddit_rss import build_rss_url, extract_subreddit_from_path, parse_rss_feed

BASES = ("https://old.reddit.com", "https://www.reddit.com")
# Reddit requires a descriptive User-Agent (https://github.com/reddit-archive/reddit/wiki/API)
USER_AGENT = "web:stallion-reddit-scraper:v1.0 (by /u/busy_evidence)"
JSON_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.reddit.com/",
}
RSS_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/atom+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.reddit.com/",
}
PAGE_DELAY_SECONDS = 1.5


class RedditHttpClient:
    """Fetch Reddit data with proxy, JSON, session cookies, and RSS fallback."""

    def __init__(self, proxy_url: str | None = None) -> None:
        self._proxy_url = proxy_url
        self._client: httpx.AsyncClient | None = None
        self._session_cookies: httpx.Cookies | None = None

    async def __aenter__(self) -> RedditHttpClient:
        self._client = httpx.AsyncClient(
            proxy=self._proxy_url,
            timeout=45.0,
            follow_redirects=True,
            headers=JSON_HEADERS,
        )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _ensure_session_cookies(self) -> None:
        """Load session cookies from old.reddit.com HTML (helps JSON on some IPs)."""
        if self._session_cookies or not self._client:
            return
        try:
            response = await self._client.get(
                "https://old.reddit.com/",
                headers={**JSON_HEADERS, "Accept": "text/html,application/xhtml+xml"},
            )
            if response.cookies:
                self._session_cookies = response.cookies
                log_info("Acquired Reddit session cookies from old.reddit.com")
        except httpx.HTTPError as exc:
            log_warning("Could not acquire session cookies: %s", exc)

    async def _get(self, url: str, *, headers: dict[str, str] | None = None) -> httpx.Response | None:
        if not self._client:
            return None
        try:
            return await self._client.get(url, headers=headers or JSON_HEADERS, cookies=self._session_cookies)
        except httpx.HTTPError as exc:
            log_warning("HTTP error for %s: %s", url, exc)
            return None

    async def fetch_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | list[Any] | None:
        """GET Reddit JSON; returns None on failure (caller may use RSS)."""
        if not self._client:
            raise RuntimeError("Client not initialized")

        await self._ensure_session_cookies()

        query = dict(params or {})
        query.setdefault("raw_json", "1")
        path = path.rstrip("/")
        if not path.endswith(".json"):
            path = f"{path}.json"
        qs = urlencode({k: v for k, v in query.items() if v is not None})

        last_status: int | None = None

        for base in BASES:
            url = f"{base}{path}?{qs}" if qs else f"{base}{path}"
            for attempt in range(2):
                response = await self._get(url)
                if not response:
                    break
                last_status = response.status_code

                if response.status_code == 403:
                    log_warning("JSON blocked (403) for %s", url)
                    break
                if response.status_code == 429:
                    wait = 3 * (attempt + 1)
                    log_warning("Rate limited (429) for %s — waiting %ss", url, wait)
                    await asyncio.sleep(wait)
                    continue
                if response.status_code != 200:
                    log_warning("HTTP %s for %s", response.status_code, url)
                    break

                if response.text[:1] not in ("{", "["):
                    log_warning("Non-JSON response from %s", url)
                    break

                try:
                    return response.json()
                except ValueError:
                    break

        return None

    async def fetch_rss_listing(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Fetch listing via public Atom/RSS feed (works when JSON is blocked)."""
        subreddit = extract_subreddit_from_path(path)
        page_params = dict(params or {})
        page_params.pop("raw_json", None)
        page_params.pop("limit", None)

        for base in BASES:
            url = build_rss_url(base, path, page_params)
            response = await self._get(url, headers=RSS_HEADERS)
            if not response:
                continue
            if response.status_code == 403:
                log_warning("RSS blocked (403) for %s", url)
                continue
            if response.status_code == 429:
                log_warning("RSS rate limited (429) for %s", url)
                await asyncio.sleep(5)
                continue
            if response.status_code != 200:
                log_warning("RSS HTTP %s for %s", response.status_code, url)
                continue

            posts, after = parse_rss_feed(response.text, subreddit=subreddit)
            if posts:
                log_info("RSS fallback returned %d posts from %s", len(posts), url)
                return posts, after

        return [], None

    async def paginate_listing(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        after: str | None = None,
        max_items: int = 100,
        deadline: float | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield posts from JSON listing, falling back to RSS when JSON is blocked."""
        cursor = after
        fetched = 0
        base_params = dict(params or {})
        base_params.setdefault("limit", 100)
        used_rss = False

        while fetched < max_items:
            if deadline and time.monotonic() >= deadline:
                break

            page_params = dict(base_params)
            if cursor:
                page_params["after"] = cursor

            if not used_rss:
                payload = await self.fetch_json(path, page_params)
                if payload and isinstance(payload, dict):
                    data = payload.get("data") or {}
                    children = data.get("children") or []
                    if children:
                        for child in children:
                            if fetched >= max_items:
                                return
                            if child.get("kind") != "t3":
                                continue
                            post_data = child.get("data")
                            if isinstance(post_data, dict):
                                post_data["_data_source"] = "json"
                                fetched += 1
                                yield post_data
                        cursor = data.get("after")
                        if not cursor:
                            break
                        await asyncio.sleep(PAGE_DELAY_SECONDS)
                        continue

                log_info("JSON unavailable for %s — switching to RSS fallback", path)
                used_rss = True

            rss_posts, next_after = await self.fetch_rss_listing(path, page_params)
            if not rss_posts:
                break

            for post in rss_posts:
                if fetched >= max_items:
                    return
                fetched += 1
                yield post

            if not next_after or next_after == cursor:
                break
            cursor = next_after
            await asyncio.sleep(PAGE_DELAY_SECONDS)

    async def fetch_post_with_comments(
        self,
        permalink: str,
        *,
        max_comments: int = 100,
    ) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """Fetch post detail and comments from JSON permalink."""
        path = permalink.rstrip("/")
        if not path.startswith("/"):
            path = f"/{path}"

        payload = await self.fetch_json(path, {"limit": min(max_comments, 100)})
        return parse_post_with_comments_payload(payload, max_comments=max_comments)


def parse_post_with_comments_payload(
    payload: dict[str, Any] | list[Any] | None,
    *,
    max_comments: int,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Parse Reddit's `[post_listing, comment_listing]` JSON payload."""
    if not payload or not isinstance(payload, list) or len(payload) < 1:
        return None, []

    listing = payload[0] if isinstance(payload[0], dict) else {}
    children = (listing.get("data") or {}).get("children") or []
    post_data = None
    for child in children:
        if child.get("kind") == "t3" and isinstance(child.get("data"), dict):
            post_data = child["data"]
            break

    comments: list[dict[str, Any]] = []
    if max_comments > 0 and len(payload) > 1:
        comment_listing = payload[1] if isinstance(payload[1], dict) else {}
        comment_children = (comment_listing.get("data") or {}).get("children") or []
        _flatten_comments(comment_children, comments, max_comments)

    return post_data, comments


def _flatten_comments(
    children: list[Any],
    out: list[dict[str, Any]],
    max_comments: int,
) -> None:
    for child in children:
        if len(out) >= max_comments:
            return
        if not isinstance(child, dict) or child.get("kind") != "t1":
            continue
        data = child.get("data")
        if not isinstance(data, dict):
            continue
        out.append(data)
        replies = data.get("replies")
        if isinstance(replies, dict):
            reply_children = (replies.get("data") or {}).get("children") or []
            _flatten_comments(reply_children, out, max_comments)
