"""Apify Actor entrypoint."""

from __future__ import annotations

from apify import Actor

from src.modes.browse import iter_discovered_posts
from src.modes.post import scrape_post_url
from src.modes.search import iter_search_posts
from src.normalize import normalize_post
from src.reddit_http import RedditHttpClient
from src.log_utils import log_info, log_warning
from src.url_utils import parse_reddit_url
from typing import Any


def _needs_full_post_fetch(inp: dict[str, Any]) -> bool:
    max_comments = int(inp.get("maxComments") or 0)
    skip_comments = bool(inp.get("skipComments", False))
    return max_comments > 0 and not skip_comments


async def _enrich_and_push(
    client: RedditHttpClient,
    post_stub: dict[str, Any],
    *,
    inp: dict[str, Any],
    max_comments: int,
    include_media: bool,
) -> dict[str, Any] | None:
    """Phase 2: fetch full post when comments or body detail needed."""
    permalink = str(post_stub.get("permalink") or "").strip()
    if not permalink:
        return normalize_post(post_stub, comments=[], include_media=include_media)

    url = f"https://www.reddit.com{permalink}" if permalink.startswith("/") else permalink
    return await scrape_post_url(
        client,
        url,
        inp=inp,
        max_comments=max_comments,
        include_media=include_media,
    )


async def _run_start_urls(
    client: RedditHttpClient,
    start_urls: list[str],
    inp: dict[str, Any],
    limits: dict[str, int],
    include_media: bool,
) -> int:
    max_items = limits["max_items"]
    max_comments = limits["max_comments"]
    full_fetch = _needs_full_post_fetch(inp)
    pushed = 0

    direct_posts = [url for url in start_urls if parse_reddit_url(url).kind == "post"]
    listing_urls = [url for url in start_urls if parse_reddit_url(url).kind != "post"]

    for url in direct_posts:
        if pushed >= max_items:
            break
        row = await scrape_post_url(
            client,
            url,
            inp=inp,
            max_comments=max_comments,
            include_media=include_media,
        )
        if row:
            await Actor.push_data(row)
            pushed += 1

    if listing_urls:
        async for stub in iter_discovered_posts(
            client,
            listing_urls,
            inp=inp,
            max_items=max_items - pushed,
            max_post_count=limits["max_post_count"],
            scroll_timeout=limits["scroll_timeout"],
        ):
            if pushed >= max_items:
                break
            try:
                if full_fetch:
                    row = await _enrich_and_push(
                        client, stub, inp=inp, max_comments=max_comments, include_media=include_media
                    )
                    if not row:
                        log_warning("Comment fetch failed for post %s — saving listing data without comments", stub.get("id"))
                        row = normalize_post(stub, comments=[], include_media=include_media)
                else:
                    row = normalize_post(stub, comments=[], include_media=include_media)
                if row:
                    await Actor.push_data(row)
                    pushed += 1
            except Exception as exc:
                log_warning("Failed to process post stub: %s", exc)

    return pushed


async def _run_searches(
    client: RedditHttpClient,
    searches: list[str],
    inp: dict[str, Any],
    limits: dict[str, int],
    include_media: bool,
) -> int:
    max_items = limits["max_items"]
    max_comments = limits["max_comments"]
    full_fetch = _needs_full_post_fetch(inp)
    pushed = 0

    async for stub in iter_search_posts(
        client,
        searches,
        inp=inp,
        max_items=max_items,
        max_post_count=limits["max_post_count"],
        scroll_timeout=limits["scroll_timeout"],
    ):
        if pushed >= max_items:
            break
        try:
            if full_fetch:
                row = await _enrich_and_push(
                    client, stub, inp=inp, max_comments=max_comments, include_media=include_media
                )
                if not row:
                    log_warning("Comment fetch failed for post %s — saving listing data without comments", stub.get("id"))
                    row = normalize_post(stub, comments=[], include_media=include_media)
            else:
                row = normalize_post(stub, comments=[], include_media=include_media)
            if row:
                await Actor.push_data(row)
                pushed += 1
        except Exception as exc:
            log_warning("Failed to process search result: %s", exc)

    return pushed


async def main() -> None:
    async with Actor:
        inp: dict[str, Any] = await Actor.get_input() or {}
        proxy_input = inp.get("proxy") or {}
        proxy_configuration = await Actor.create_proxy_configuration(
            actor_proxy_input=proxy_input,
            groups=["RESIDENTIAL"],
        )
        proxy_url = None
        if proxy_configuration:
            proxy_url = await proxy_configuration.new_url(session_id="reddit_scraper")
            log_info("Using Apify residential proxy for Reddit requests.")
        elif proxy_input.get("useApifyProxy"):
            log_warning(
                "Proxy was requested (useApifyProxy: true) but no proxy configuration was created. "
                "Check your Apify plan includes residential proxy access."
            )
        else:
            log_warning("Running without proxy — Reddit may block datacenter IPs.")

        limits = {
            "max_items": max(1, int(inp.get("maxItems") or 100)),
            "max_post_count": max(1, int(inp.get("maxPostCount") or 100)),
            "max_comments": max(0, int(inp.get("maxComments") or 0)),
            "scroll_timeout": max(1, int(inp.get("scrollTimeout") or 40)),
        }
        include_media = bool(inp.get("includeMediaLinks", False))

        start_urls = [u["url"] for u in (inp.get("startUrls") or []) if isinstance(u, dict) and u.get("url")]
        searches = [str(s).strip() for s in (inp.get("searches") or []) if str(s).strip()]

        async with RedditHttpClient(proxy_url=proxy_url) as client:
            if start_urls:
                Actor.log.info("Found startUrl. Search params will be ignored.")
                pushed = await _run_start_urls(client, start_urls, inp, limits, include_media)
            elif searches:
                pushed = await _run_searches(client, searches, inp, limits, include_media)
            else:
                raise ValueError("Provide startUrls or searches in the Actor input.")

        Actor.log.info("Done — %d items pushed to dataset.", pushed)
