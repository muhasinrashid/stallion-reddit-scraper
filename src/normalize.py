"""Map Reddit JSON to reddit-scraper-lite compatible dataset rows."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

REMOVED = frozenset({"[removed]", "[deleted]"})


def _utc_iso(ts: float | int | str | None) -> str:
    if ts is None:
        return ""
    if isinstance(ts, str):
        return ts if ts.endswith("Z") else ts
    try:
        return datetime.fromtimestamp(float(ts), tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    except (TypeError, ValueError, OSError):
        return ""


def _bare_id(full_id: str) -> str:
    s = str(full_id or "").strip()
    if s.startswith("t3_") or s.startswith("t1_"):
        return s[3:]
    return s


def _clean_body(text: str | None) -> str:
    body = str(text or "").strip()
    if body in REMOVED:
        return ""
    return body


def normalize_comment(raw: dict[str, Any], *, parent_id: str = "") -> dict[str, Any] | None:
    body = _clean_body(raw.get("body"))
    if not body:
        return None
    parsed_id = _bare_id(str(raw.get("id") or raw.get("name") or ""))
    if not parsed_id:
        return None
    return {
        "parsedId": parsed_id,
        "body": body,
        "username": str(raw.get("author") or "[deleted]"),
        "upVotes": int(raw.get("score") or 0),
        "createdAt": _utc_iso(raw.get("created_utc")),
        "parentId": str(raw.get("parent_id") or parent_id or ""),
    }


def normalize_post(
    raw: dict[str, Any],
    *,
    comments: list[dict[str, Any]] | None = None,
    include_media: bool = False,
    scraped_at: str | None = None,
) -> dict[str, Any]:
    """Convert Reddit post data dict to public dataset row."""
    parsed_id = _bare_id(str(raw.get("id") or raw.get("name") or ""))
    subreddit = str(raw.get("subreddit") or "").strip()
    subreddit_lower = subreddit.lower()
    permalink = str(raw.get("permalink") or "").strip()
    if permalink and not permalink.startswith("http"):
        url = f"https://www.reddit.com{permalink}"
    else:
        url = permalink or str(raw.get("url") or "")

    row: dict[str, Any] = {
        "dataType": "post",
        "parsedId": parsed_id,
        "id": str(raw.get("name") or f"t3_{parsed_id}"),
        "url": url,
        "title": str(raw.get("title") or "").strip(),
        "body": _clean_body(raw.get("selftext")),
        "parsedCommunityName": subreddit_lower,
        "communityName": f"r/{subreddit}" if subreddit else "",
        "username": str(raw.get("author") or "[deleted]"),
        "upVotes": int(raw.get("score") or 0),
        "numberOfComments": int(raw.get("num_comments") or 0),
        "createdAt": _utc_iso(raw.get("created_utc")),
        "scrapedAt": scraped_at or datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "comments": [],
    }

    if comments is not None:
        parent_id = str(raw.get("name") or f"t3_{parsed_id}")
        normalized_comments: list[dict[str, Any]] = []
        for c in comments:
            if isinstance(c, dict):
                if "body" in c and "created_utc" not in c and "createdAt" in c:
                    normalized_comments.append(c)
                else:
                    nc = normalize_comment(c, parent_id=parent_id)
                    if nc:
                        normalized_comments.append(nc)
        row["comments"] = normalized_comments
        if normalized_comments:
            row["numberOfComments"] = max(row["numberOfComments"], len(normalized_comments))

    if include_media:
        row["over18"] = bool(raw.get("over_18"))
        row["isVideo"] = bool(raw.get("is_video"))
        row["upVoteRatio"] = raw.get("upvote_ratio")
        row["flair"] = str(raw.get("link_flair_text") or "")
        media_urls: list[str] = []
        if raw.get("url") and raw.get("is_video"):
            media_urls.append(str(raw["url"]))
        if raw.get("thumbnail") and str(raw["thumbnail"]).startswith("http"):
            media_urls.append(str(raw["thumbnail"]))
        preview = raw.get("preview") or {}
        if isinstance(preview, dict):
            for image in (preview.get("images") or []):
                if isinstance(image, dict):
                    source = image.get("source") or {}
                    if isinstance(source, dict) and source.get("url"):
                        media_urls.append(str(source["url"]).replace("&amp;", "&"))
        row["imageUrls"] = media_urls
        row["videoUrls"] = [u for u in media_urls if "video" in u or raw.get("is_video")]

    source = raw.get("_data_source")
    if source == "rss":
        row["dataSource"] = "rss"

    return row


def post_created_ts(raw: dict[str, Any]) -> float:
    try:
        return float(raw.get("created_utc") or 0)
    except (TypeError, ValueError):
        return 0.0


def parse_date_limit(date_str: str | None) -> float | None:
    """Parse YYYY-MM-DD to UTC timestamp (start of day)."""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(str(date_str).strip(), "%Y-%m-%d").replace(tzinfo=UTC)
        return dt.timestamp()
    except ValueError:
        return None


def parse_date_limit_end(date_str: str | None) -> float | None:
    """Parse YYYY-MM-DD to UTC timestamp (end of day)."""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(str(date_str).strip(), "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=UTC
        )
        return dt.timestamp()
    except ValueError:
        return None


def passes_date_limit(raw: dict[str, Any], min_ts: float | None) -> bool:
    if min_ts is None:
        return True
    return post_created_ts(raw) >= min_ts


def passes_date_range(
    raw: dict[str, Any],
    *,
    min_ts: float | None = None,
    max_ts: float | None = None,
) -> bool:
    ts = post_created_ts(raw)
    if min_ts is not None and ts < min_ts:
        return False
    if max_ts is not None and ts > max_ts:
        return False
    return True


def normalize_search_community(raw: dict[str, Any]) -> dict[str, Any]:
    name = str(raw.get("display_name") or raw.get("name") or "").strip()
    return {
        "dataType": "community",
        "parsedCommunityName": name.lower(),
        "communityName": f"r/{name}" if name else "",
        "title": str(raw.get("title") or ""),
        "description": str(raw.get("public_description") or raw.get("description") or ""),
        "subscribers": int(raw.get("subscribers") or 0),
        "url": f"https://www.reddit.com/r/{name}/" if name else "",
    }


def normalize_search_user(raw: dict[str, Any]) -> dict[str, Any]:
    name = str(raw.get("name") or "").strip()
    return {
        "dataType": "user",
        "username": name,
        "url": f"https://www.reddit.com/user/{name}/" if name else "",
        "linkKarma": int(raw.get("link_karma") or 0),
        "commentKarma": int(raw.get("comment_karma") or 0),
    }


def normalize_search_comment_row(raw: dict[str, Any]) -> dict[str, Any] | None:
    row = normalize_comment(raw)
    if not row:
        return None
    row["dataType"] = "comment"
    row["communityName"] = str(raw.get("subreddit_name_prefixed") or "")
    row["parsedCommunityName"] = str(raw.get("subreddit") or "").lower()
    permalink = str(raw.get("permalink") or "").strip()
    if permalink and not permalink.startswith("http"):
        row["url"] = f"https://www.reddit.com{permalink}"
    elif permalink:
        row["url"] = permalink
    return row
