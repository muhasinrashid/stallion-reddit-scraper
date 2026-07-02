"""Scrape a single Reddit post and its comments."""

from __future__ import annotations

from typing import Any

from src.log_utils import log_info, log_warning
from src.normalize import normalize_post, parse_date_limit, passes_date_limit
from src.reddit_http import RedditHttpClient
from src.url_utils import parse_reddit_url


async def scrape_post_url(
    client: RedditHttpClient,
    url: str,
    *,
    inp: dict[str, Any],
    max_comments: int,
    include_media: bool,
) -> dict[str, Any] | None:
    """Fetch and normalize a single post URL."""
    parsed = parse_reddit_url(url, default_include_nsfw=bool(inp.get("includeNSFW", False)))
    post_date_limit = parse_date_limit(inp.get("postDateLimit"))
    comment_date_limit = parse_date_limit(inp.get("commentDateLimit"))

    permalink = parsed.raw_url
    if "reddit.com" in permalink:
        from urllib.parse import urlparse

        path = urlparse(permalink).path
        permalink = path

    log_info("Processing %s ...", url)

    try:
        post_data, raw_comments = await client.fetch_post_with_comments(
            permalink,
            max_comments=max_comments,
        )
    except Exception as exc:
        log_warning("Failed to fetch post %s: %s", url, exc)
        return None

    if not post_data:
        log_warning("No post data returned for %s", url)
        return None

    if not passes_date_limit(post_data, post_date_limit):
        return None

    comments = raw_comments
    if comment_date_limit is not None:
        comments = [c for c in raw_comments if passes_date_limit(c, comment_date_limit)]

    return normalize_post(
        post_data,
        comments=comments if max_comments > 0 else [],
        include_media=include_media,
    )
