"""Playwright-based Reddit fetcher for JSON-blocked pages."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode, urlparse

from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from src.log_utils import log_info, log_warning
from src.reddit_http import BASES, USER_AGENT

BROWSER_TIMEOUT_MS = 60_000


def _playwright_proxy(proxy_url: str) -> dict[str, str]:
    """Convert an Apify-style proxy URL into Playwright proxy settings."""
    parsed = urlparse(proxy_url)
    if not parsed.hostname:
        raise ValueError(f"Invalid proxy URL: {proxy_url}")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    proxy: dict[str, str] = {"server": f"{parsed.scheme}://{parsed.hostname}:{port}"}
    if parsed.username:
        proxy["username"] = parsed.username
    if parsed.password:
        proxy["password"] = parsed.password
    return proxy


class RedditBrowserFetcher:
    """Fetch Reddit JSON through a headless browser when HTTP is blocked."""

    def __init__(self, proxy_url: str | None = None) -> None:
        self._proxy_url = proxy_url
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def __aenter__(self) -> RedditBrowserFetcher:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def _ensure_context(self) -> BrowserContext:
        if self._context:
            return self._context

        self._playwright = await async_playwright().start()
        launch_kwargs: dict[str, Any] = {"headless": True}
        if self._proxy_url:
            launch_kwargs["proxy"] = _playwright_proxy(self._proxy_url)

        self._browser = await self._playwright.chromium.launch(**launch_kwargs)
        self._context = await self._browser.new_context(user_agent=USER_AGENT)
        log_info("Playwright browser session started for Reddit fallback.")
        return self._context

    async def close(self) -> None:
        if self._context:
            await self._context.close()
            self._context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def fetch_json(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | list[Any] | None:
        """Load a Reddit `.json` endpoint in the browser and parse the response body."""
        context = await self._ensure_context()
        query = dict(params or {})
        query.setdefault("raw_json", "1")
        path = path.rstrip("/")
        if not path.endswith(".json"):
            path = f"{path}.json"
        qs = urlencode({k: v for k, v in query.items() if v is not None})

        for base in BASES:
            url = f"{base}{path}?{qs}" if qs else f"{base}{path}"
            page = await context.new_page()
            try:
                log_info("Browser fetch: %s", url)
                response = await page.goto(url, wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT_MS)
                if not response:
                    continue
                if response.status == 403:
                    log_warning("Browser blocked (403) for %s", url)
                    continue
                if response.status != 200:
                    log_warning("Browser HTTP %s for %s", response.status, url)
                    continue

                text = (await response.text()).strip()
                if not text or text[0] not in ("{", "["):
                    log_warning("Browser returned non-JSON body for %s", url)
                    continue

                return json.loads(text)
            except (json.JSONDecodeError, TimeoutError) as exc:
                log_warning("Browser fetch failed for %s: %s", url, exc)
            finally:
                await page.close()

        return None
