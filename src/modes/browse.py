"""Browse subreddit listings from startUrls."""

from __future__ import annotations

import time
from typing import Any, AsyncIterator

from src.log_utils import log_info, log_warning
from src.normalize import passes_date_limit, parse_date_limit
from src.reddit_http import RedditHttpClient
from src.url_utils import ParsedUrl, listing_json_path, listing_params, parse_reddit_url


async def iter_discovered_posts(
    client: RedditHttpClient,
    start_urls: list[str],
    *,
    inp: dict[str, Any],
    max_items: int,
    max_post_count: int,
    scroll_timeout: int,
) -> AsyncIterator[dict[str, Any]]:
    """Phase 1: discover post stubs from listing startUrls."""
    include_nsfw = bool(inp.get("includeNSFW", False))
    post_date_limit = parse_date_limit(inp.get("postDateLimit"))
    deadline = time.monotonic() + scroll_timeout
    total = 0

    for url in start_urls:
        if total >= max_items:
            break

        parsed = parse_reddit_url(url, default_include_nsfw=include_nsfw)
        if parsed.kind == "post":
            continue
        if parsed.kind != "listing":
            log_warning("Skipping unrecognized URL: %s", url)
            continue

        per_url_cap = min(max_post_count, max_items - total)
        path = listing_json_path(parsed.subreddit, parsed.sort)
        params = listing_params(include_nsfw=parsed.include_nsfw or include_nsfw, after=parsed.after)
        log_info("Fetching listing %s (max %d posts)", path, per_url_cap)

        url_deadline = min(deadline, time.monotonic() + scroll_timeout)
        count_before = total

        async for post_data in client.paginate_listing(
            path,
            params=params,
            after=parsed.after or None,
            max_items=per_url_cap,
            deadline=url_deadline,
        ):
            if total >= max_items:
                break
            if not passes_date_limit(post_data, post_date_limit):
                continue
            total += 1
            yield post_data

        if time.monotonic() >= deadline:
            log_warning(
                "SCROLL TIMEOUT REACHED, Try increasing the value of 'scrollTimeout' input`s parameter "
                "if this is limiting your results",
            )
            log_warning('{"url":"%s","scrollTimeout":%d}', url, scroll_timeout * 1000)

        log_info("%d posts urls added to queue from %s", total - count_before, url)


async def iter_post_urls(
    start_urls: list[str],
    *,
    include_nsfw: bool = False,
) -> AsyncIterator[tuple[str, ParsedUrl]]:
    """Yield direct post URLs from startUrls."""
    for url in start_urls:
        parsed = parse_reddit_url(url, default_include_nsfw=include_nsfw)
        if parsed.kind == "post":
            yield url, parsed
