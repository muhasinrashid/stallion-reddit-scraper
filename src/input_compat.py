"""Normalize legacy Stallion and harshmaur-style Actor input into RunConfig."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _first_str(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _coerce_urls(items: Any) -> list[str]:
    if not items:
        return []
    urls: list[str] = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and item.get("url"):
                urls.append(str(item["url"]).strip())
            elif isinstance(item, str) and item.strip():
                urls.append(item.strip())
    return urls


def _coerce_terms(items: Any) -> list[str]:
    if not items:
        return []
    if not isinstance(items, list):
        return []
    return [str(item).strip() for item in items if str(item).strip()]


@dataclass
class RunConfig:
    """Canonical run settings used by all modes."""

    start_urls: list[str] = field(default_factory=list)
    searches: list[str] = field(default_factory=list)
    search_community: str | None = None
    sort: str = "new"
    time_filter: str = "all"
    posted_after: str | None = None
    posted_before: str | None = None
    commented_after: str | None = None
    commented_before: str | None = None
    max_items: int = 100
    max_post_count: int = 100
    max_comments: int = 0
    crawl_comments: bool = False
    scroll_timeout: int = 40
    include_nsfw: bool = False
    search_posts: bool = True
    search_comments: bool = False
    search_communities: bool = False
    search_users: bool = False
    skip_comments: bool = False
    include_media: bool = False
    fast_mode: bool = True
    only_with_flair: str | None = None
    proxy: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_actor_input(cls, inp: dict[str, Any] | None) -> RunConfig:
        data = dict(inp or {})

        start_urls = _coerce_urls(data.get("startUrls"))
        subreddit_urls = _coerce_urls(data.get("subredditUrls"))
        for url in subreddit_urls:
            if url not in start_urls:
                start_urls.append(url)

        searches = _coerce_terms(data.get("searchTerms")) or _coerce_terms(data.get("searches"))

        community = _first_str(data.get("withinCommunity"), data.get("searchCommunityName"))
        if community:
            community = community.lstrip("r/").strip() or None

        max_items = max(1, int(data.get("maxPostsCount") or data.get("maxItems") or 100))
        max_post_count = max(1, int(data.get("maxPostsCount") or data.get("maxPostCount") or max_items))
        max_comments = max(0, int(data.get("maxCommentsPerPost") or data.get("maxComments") or 0))
        crawl_comments = bool(data.get("crawlCommentsPerPost", max_comments > 0))

        posted_after = _first_str(data.get("postedAfter"), data.get("postDateLimit"))
        posted_before = _first_str(data.get("postedBefore"))
        commented_after = _first_str(data.get("commentedAfter"), data.get("commentDateLimit"))
        commented_before = _first_str(data.get("commentedBefore"))

        return cls(
            start_urls=start_urls,
            searches=searches,
            search_community=community,
            sort=str(data.get("sort") or "new"),
            time_filter=str(data.get("time") or "all"),
            posted_after=posted_after,
            posted_before=posted_before,
            commented_after=commented_after,
            commented_before=commented_before,
            max_items=max_items,
            max_post_count=max_post_count,
            max_comments=max_comments,
            crawl_comments=crawl_comments,
            scroll_timeout=max(1, int(data.get("scrollTimeout") or 40)),
            include_nsfw=bool(data.get("includeNSFW", False)),
            search_posts=bool(data.get("searchPosts", True)),
            search_comments=bool(data.get("searchComments", False)),
            search_communities=bool(data.get("searchCommunities", False)),
            search_users=bool(data.get("searchUsers", False)),
            skip_comments=bool(data.get("skipComments", False)),
            include_media=bool(data.get("includeMediaLinks", False)),
            fast_mode=bool(data.get("fastMode", True)),
            only_with_flair=_first_str(data.get("onlyWithFlair")),
            proxy=dict(data.get("proxy") or {}),
            raw=data,
        )

    def as_mode_input(self) -> dict[str, Any]:
        """Dict passed to mode modules — legacy keys plus normalized aliases."""
        out = dict(self.raw)
        out.update(
            {
                "startUrls": [{"url": url} for url in self.start_urls],
                "searches": self.searches,
                "searchTerms": self.searches,
                "searchCommunityName": self.search_community or "",
                "withinCommunity": self.search_community or "",
                "sort": self.sort,
                "time": self.time_filter,
                "postDateLimit": self.posted_after or "",
                "postedAfter": self.posted_after or "",
                "postedBefore": self.posted_before or "",
                "commentDateLimit": self.commented_after or "",
                "commentedAfter": self.commented_after or "",
                "commentedBefore": self.commented_before or "",
                "maxItems": self.max_items,
                "maxPostCount": self.max_post_count,
                "maxPostsCount": self.max_items,
                "maxComments": self.max_comments,
                "maxCommentsPerPost": self.max_comments,
                "crawlCommentsPerPost": self.crawl_comments,
                "scrollTimeout": self.scroll_timeout,
                "includeNSFW": self.include_nsfw,
                "searchPosts": self.search_posts,
                "searchComments": self.search_comments,
                "searchCommunities": self.search_communities,
                "searchUsers": self.search_users,
                "skipComments": self.skip_comments,
                "includeMediaLinks": self.include_media,
                "fastMode": self.fast_mode,
                "onlyWithFlair": self.only_with_flair or "",
            }
        )
        return out

    @property
    def limits(self) -> dict[str, int]:
        return {
            "max_items": self.max_items,
            "max_post_count": self.max_post_count,
            "max_comments": self.max_comments,
            "scroll_timeout": self.scroll_timeout,
        }

    def needs_full_post_fetch(self) -> bool:
        return self.crawl_comments and self.max_comments > 0 and not self.skip_comments
