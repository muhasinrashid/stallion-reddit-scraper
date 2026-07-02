"""Reddit keyword search mode with browse fallback."""

from __future__ import annotations

import time
from typing import Any, AsyncIterator

from src.log_utils import log_info, log_warning
from src.normalize import passes_date_limit, parse_date_limit
from src.reddit_http import RedditHttpClient
from src.url_utils import listing_json_path, listing_params


def _search_path(subreddit: str | None) -> str:
    if subreddit:
        return f"/r/{subreddit}/search"
    return "/search"


async def iter_search_posts(
    client: RedditHttpClient,
    searches: list[str],
    *,
    inp: dict[str, Any],
    max_items: int,
    max_post_count: int,
    scroll_timeout: int,
) -> AsyncIterator[dict[str, Any]]:
    """Discover posts via Reddit search; fallback to browse on empty niche subs."""
    include_nsfw = bool(inp.get("includeNSFW", False))
    post_date_limit = parse_date_limit(inp.get("postDateLimit"))
    subreddit = str(inp.get("searchCommunityName") or "").strip().lstrip("r/")
    sort = str(inp.get("sort") or "new")
    time_filter = str(inp.get("time") or "all")
    deadline = time.monotonic() + scroll_timeout
    total = 0
    seen_ids: set[str] = set()

    queries = [q.strip() for q in searches if str(q).strip()]
    if not queries:
        return

    for query in queries:
        if total >= max_items or time.monotonic() >= deadline:
            break

        per_query_cap = min(max_post_count, max_items - total)
        params: dict[str, Any] = {
            "q": query,
            "sort": sort,
            "limit": 100,
        }
        if subreddit:
            params["restrict_sr"] = "1"
        if sort in ("top", "relevance", "comments"):
            params["t"] = time_filter
        if include_nsfw:
            params["include_over_18"] = "on"

        path = _search_path(subreddit or None)
        found_for_query = 0

        async for post_data in client.paginate_listing(
            path,
            params=params,
            max_items=per_query_cap,
            deadline=deadline,
        ):
            if total >= max_items:
                return
            post_id = str(post_data.get("id") or "")
            if post_id in seen_ids:
                continue
            if not passes_date_limit(post_data, post_date_limit):
                continue
            seen_ids.add(post_id)
            total += 1
            found_for_query += 1
            yield post_data

        if found_for_query == 0 and subreddit:
            log_info(
                "Search returned 0 results for %r in r/%s — falling back to browse /new/",
                query,
                subreddit,
            )
            browse_path = listing_json_path(subreddit, "new")
            browse_params = listing_params(include_nsfw=include_nsfw)
            query_lower = query.lower()

            async for post_data in client.paginate_listing(
                browse_path,
                params=browse_params,
                max_items=per_query_cap,
                deadline=deadline,
            ):
                if total >= max_items:
                    return
                post_id = str(post_data.get("id") or "")
                if post_id in seen_ids:
                    continue
                if not passes_date_limit(post_data, post_date_limit):
                    continue
                title = str(post_data.get("title") or "").lower()
                body = str(post_data.get("selftext") or "").lower()
                if query_lower not in title and query_lower not in body:
                    continue
                seen_ids.add(post_id)
                total += 1
                yield post_data

        if time.monotonic() >= deadline:
            log_warning(
                "SCROLL TIMEOUT REACHED, Try increasing the value of 'scrollTimeout' input`s parameter "
                "if this is limiting your results",
            )
            log_warning('{"scrollTimeout":%d}', scroll_timeout * 1000)
            break
