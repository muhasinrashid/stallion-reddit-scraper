"""Parse and classify Reddit URLs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

POST_RE = re.compile(r"/r/([^/]+)/comments/([^/]+)", re.I)
LISTING_RE = re.compile(r"/r/([^/]+)(?:/(new|hot|top|rising|controversial))/?", re.I)


@dataclass(frozen=True)
class ParsedUrl:
    kind: str  # listing | post | unknown
    subreddit: str = ""
    sort: str = "new"
    post_id: str = ""
    after: str = ""
    include_nsfw: bool = False
    raw_url: str = ""


def parse_reddit_url(url: str, *, default_include_nsfw: bool = False) -> ParsedUrl:
    parsed = urlparse(url.strip())
    path = parsed.path or ""
    qs = parse_qs(parsed.query)
    include_nsfw = default_include_nsfw or qs.get("include_over_18", ["off"])[0] == "on"
    after = qs.get("after", [""])[0]

    post_match = POST_RE.search(path)
    if post_match:
        return ParsedUrl(
            kind="post",
            subreddit=post_match.group(1),
            post_id=post_match.group(2),
            after=after,
            include_nsfw=include_nsfw,
            raw_url=url,
        )

    listing_match = LISTING_RE.search(path)
    if listing_match:
        sort = listing_match.group(2) or "new"
        return ParsedUrl(
            kind="listing",
            subreddit=listing_match.group(1),
            sort=sort.lower(),
            after=after,
            include_nsfw=include_nsfw,
            raw_url=url,
        )

    return ParsedUrl(kind="unknown", raw_url=url, include_nsfw=include_nsfw, after=after)


def listing_json_path(subreddit: str, sort: str = "new") -> str:
    return f"/r/{subreddit}/{sort}"


def listing_params(*, include_nsfw: bool, after: str = "") -> dict[str, str]:
    params: dict[str, str] = {}
    if include_nsfw:
        params["include_over_18"] = "on"
    if after:
        params["after"] = after
    return params
