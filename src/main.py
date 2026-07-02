"""Apify Actor entrypoint."""

from __future__ import annotations

from typing import Any

from apify import Actor

from src.input_compat import RunConfig
from src.modes.browse import iter_discovered_posts
from src.modes.post import scrape_post_url
from src.modes.search import (
    iter_search_comments,
    iter_search_communities,
    iter_search_posts,
    iter_search_users,
)
from src.normalize import normalize_post
from src.reddit_client import RedditClient
from src.log_utils import log_info, log_warning
from src.url_utils import parse_reddit_url


async def _enrich_and_push(
    client: RedditClient,
    post_stub: dict[str, Any],
    *,
    inp: dict[str, Any],
    max_comments: int,
    include_media: bool,
) -> dict[str, Any] | None:
    """Fetch full post when comments or body detail needed."""
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
    client: RedditClient,
    config: RunConfig,
) -> int:
    inp = config.as_mode_input()
    limits = config.limits
    max_items = limits["max_items"]
    max_comments = limits["max_comments"]
    include_media = config.include_media
    full_fetch = config.needs_full_post_fetch()
    pushed = 0

    start_urls = config.start_urls
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
                        log_warning(
                            "Comment fetch failed for post %s — saving listing data without comments",
                            stub.get("id"),
                        )
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
    client: RedditClient,
    config: RunConfig,
) -> int:
    inp = config.as_mode_input()
    limits = config.limits
    max_items = limits["max_items"]
    max_comments = limits["max_comments"]
    include_media = config.include_media
    full_fetch = config.needs_full_post_fetch()
    pushed = 0
    searches = config.searches

    search_iters = (
        iter_search_posts,
        iter_search_comments,
        iter_search_communities,
        iter_search_users,
    )

    for search_iter in search_iters:
        async for row in search_iter(
            client,
            searches,
            inp=inp,
            max_items=max_items - pushed,
            max_post_count=limits["max_post_count"],
            scroll_timeout=limits["scroll_timeout"],
        ):
            if pushed >= max_items:
                return pushed

            if row.get("dataType") == "post" and full_fetch:
                permalink = str(row.get("url") or "")
                if permalink:
                    enriched = await scrape_post_url(
                        client,
                        permalink,
                        inp=inp,
                        max_comments=max_comments,
                        include_media=include_media,
                    )
                    if enriched:
                        row = enriched

            try:
                await Actor.push_data(row)
                pushed += 1
            except Exception as exc:
                log_warning("Failed to process search result: %s", exc)

    return pushed


async def main() -> None:
    async with Actor:
        raw_input: dict[str, Any] = await Actor.get_input() or {}
        config = RunConfig.from_actor_input(raw_input)

        proxy_configuration = await Actor.create_proxy_configuration(
            actor_proxy_input=config.proxy,
            groups=["RESIDENTIAL"],
        )
        proxy_url = None
        if proxy_configuration:
            proxy_url = await proxy_configuration.new_url(session_id="reddit_scraper")
            log_info("Using Apify residential proxy for Reddit requests.")
        elif config.proxy.get("useApifyProxy"):
            log_warning(
                "Proxy was requested (useApifyProxy: true) but no proxy configuration was created. "
                "Check your Apify plan includes residential proxy access."
            )
        else:
            log_warning("Running without proxy — Reddit may block datacenter IPs.")

        async with RedditClient(proxy_url=proxy_url) as client:
            if config.start_urls:
                Actor.log.info("Found startUrl. Search params will be ignored.")
                pushed = await _run_start_urls(client, config)
            elif config.searches:
                pushed = await _run_searches(client, config)
            else:
                raise ValueError("Provide startUrls, subredditUrls, searchTerms, or searches in the Actor input.")

        Actor.log.info("Done — %d items pushed to dataset.", pushed)
