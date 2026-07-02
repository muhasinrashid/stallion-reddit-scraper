"""Reddit keyword search mode with browse fallback and multi-entity search."""

from __future__ import annotations

import time
from typing import Any, AsyncIterator, Literal

from src.log_utils import log_info, log_warning
from src.normalize import (
    normalize_post,
    normalize_search_comment_row,
    normalize_search_community,
    normalize_search_user,
    parse_date_limit,
    parse_date_limit_end,
    passes_date_range,
)
from src.reddit_client import RedditClient
from src.url_utils import listing_json_path, listing_params

SearchResultType = Literal["post", "comment", "community", "user"]

_SEARCH_TYPES: dict[SearchResultType, tuple[str, frozenset[str]]] = {
    "post": ("link", frozenset({"t3"})),
    "comment": ("comment", frozenset({"t1"})),
    "community": ("sr", frozenset({"t5"})),
    "user": ("user", frozenset({"t2"})),
}


def _search_path(subreddit: str | None) -> str:
    if subreddit:
        return f"/r/{subreddit}/search"
    return "/search"


def _post_date_bounds(inp: dict[str, Any]) -> tuple[float | None, float | None]:
    return (
        parse_date_limit(inp.get("postedAfter") or inp.get("postDateLimit")),
        parse_date_limit_end(inp.get("postedBefore")),
    )


def _comment_date_bounds(inp: dict[str, Any]) -> tuple[float | None, float | None]:
    return (
        parse_date_limit(inp.get("commentedAfter") or inp.get("commentDateLimit")),
        parse_date_limit_end(inp.get("commentedBefore")),
    )


def _matches_flair(post_data: dict[str, Any], flair: str | None) -> bool:
    if not flair:
        return True
    return str(post_data.get("link_flair_text") or "").strip().lower() == flair.strip().lower()


async def _iter_search_type(
    client: RedditClient,
    *,
    queries: list[str],
    result_type: SearchResultType,
    inp: dict[str, Any],
    max_items: int,
    max_post_count: int,
    scroll_timeout: int,
) -> AsyncIterator[dict[str, Any]]:
    include_nsfw = bool(inp.get("includeNSFW", False))
    posted_min, posted_max = _post_date_bounds(inp)
    comment_min, comment_max = _comment_date_bounds(inp)
    subreddit = str(inp.get("searchCommunityName") or inp.get("withinCommunity") or "").strip().lstrip("r/")
    sort = str(inp.get("sort") or "new")
    time_filter = str(inp.get("time") or "all")
    only_flair = str(inp.get("onlyWithFlair") or "").strip() or None
    deadline = time.monotonic() + scroll_timeout
    total = 0
    seen_ids: set[str] = set()

    reddit_type, kinds = _SEARCH_TYPES[result_type]

    for query in queries:
        if total >= max_items or time.monotonic() >= deadline:
            break

        per_query_cap = min(max_post_count, max_items - total)
        params: dict[str, Any] = {
            "q": query,
            "sort": sort,
            "limit": 100,
            "type": reddit_type,
        }
        if subreddit:
            params["restrict_sr"] = "1"
        if sort in ("top", "relevance", "comments"):
            params["t"] = time_filter
        if include_nsfw:
            params["include_over_18"] = "on"

        path = _search_path(subreddit or None)
        found_for_query = 0

        async for item_data in client.paginate_listing(
            path,
            params=params,
            max_items=per_query_cap,
            deadline=deadline,
            kinds=kinds,
        ):
            if total >= max_items:
                return

            item_id = str(item_data.get("id") or item_data.get("name") or "")
            if item_id in seen_ids:
                continue

            if result_type == "post":
                if not passes_date_range(item_data, min_ts=posted_min, max_ts=posted_max):
                    continue
                if not _matches_flair(item_data, only_flair):
                    continue
                seen_ids.add(item_id)
                total += 1
                found_for_query += 1
                yield normalize_post(item_data, comments=[])
                continue

            if result_type == "comment":
                if not passes_date_range(item_data, min_ts=comment_min, max_ts=comment_max):
                    continue
                row = normalize_search_comment_row(item_data)
                if not row:
                    continue
                seen_ids.add(item_id)
                total += 1
                found_for_query += 1
                yield row
                continue

            if result_type == "community":
                seen_ids.add(item_id)
                total += 1
                found_for_query += 1
                yield normalize_search_community(item_data)
                continue

            if result_type == "user":
                seen_ids.add(item_id)
                total += 1
                found_for_query += 1
                yield normalize_search_user(item_data)

        if found_for_query == 0 and result_type == "post" and subreddit:
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
                if not passes_date_range(post_data, min_ts=posted_min, max_ts=posted_max):
                    continue
                if not _matches_flair(post_data, only_flair):
                    continue
                title = str(post_data.get("title") or "").lower()
                body = str(post_data.get("selftext") or "").lower()
                if query_lower not in title and query_lower not in body:
                    continue
                seen_ids.add(post_id)
                total += 1
                yield normalize_post(post_data, comments=[])

        if time.monotonic() >= deadline:
            log_warning(
                "SCROLL TIMEOUT REACHED, Try increasing the value of 'scrollTimeout' input`s parameter "
                "if this is limiting your results",
            )
            log_warning('{"scrollTimeout":%d}', scroll_timeout * 1000)
            break


async def iter_search_posts(
    client: RedditClient,
    searches: list[str],
    *,
    inp: dict[str, Any],
    max_items: int,
    max_post_count: int,
    scroll_timeout: int,
) -> AsyncIterator[dict[str, Any]]:
    """Discover posts via Reddit search; fallback to browse on empty niche subs."""
    if not bool(inp.get("searchPosts", True)):
        return

    async for row in _iter_search_type(
        client,
        queries=searches,
        result_type="post",
        inp=inp,
        max_items=max_items,
        max_post_count=max_post_count,
        scroll_timeout=scroll_timeout,
    ):
        yield row


async def iter_search_comments(
    client: RedditClient,
    searches: list[str],
    *,
    inp: dict[str, Any],
    max_items: int,
    max_post_count: int,
    scroll_timeout: int,
) -> AsyncIterator[dict[str, Any]]:
    if not bool(inp.get("searchComments", False)):
        return

    async for row in _iter_search_type(
        client,
        queries=searches,
        result_type="comment",
        inp=inp,
        max_items=max_items,
        max_post_count=max_post_count,
        scroll_timeout=scroll_timeout,
    ):
        yield row


async def iter_search_communities(
    client: RedditClient,
    searches: list[str],
    *,
    inp: dict[str, Any],
    max_items: int,
    max_post_count: int,
    scroll_timeout: int,
) -> AsyncIterator[dict[str, Any]]:
    if not bool(inp.get("searchCommunities", False)):
        return

    async for row in _iter_search_type(
        client,
        queries=searches,
        result_type="community",
        inp=inp,
        max_items=max_items,
        max_post_count=max_post_count,
        scroll_timeout=scroll_timeout,
    ):
        yield row


async def iter_search_users(
    client: RedditClient,
    searches: list[str],
    *,
    inp: dict[str, Any],
    max_items: int,
    max_post_count: int,
    scroll_timeout: int,
) -> AsyncIterator[dict[str, Any]]:
    if not bool(inp.get("searchUsers", False)):
        return

    async for row in _iter_search_type(
        client,
        queries=searches,
        result_type="user",
        inp=inp,
        max_items=max_items,
        max_post_count=max_post_count,
        scroll_timeout=scroll_timeout,
    ):
        yield row
