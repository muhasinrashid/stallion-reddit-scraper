"""Reddit public Atom/RSS feed parser — fallback when JSON API returns 403."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode, urlparse
from xml.etree import ElementTree as ET

from src.log_utils import log_info, log_warning

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
POST_ID_RE = re.compile(r"/comments/([a-z0-9]+)/", re.I)
HTML_TAG_RE = re.compile(r"<[^>]+>")


def listing_rss_path(path: str) -> str:
    """Convert /r/sub/new to /r/sub/new/.rss"""
    path = path.rstrip("/")
    if path.endswith(".json"):
        path = path[:-5]
    if not path.endswith(".rss"):
        path = f"{path}/.rss"
    return path


def _parse_published(value: str) -> float:
    if not value:
        return 0.0
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.timestamp()
    except ValueError:
        return 0.0


def _strip_html(text: str) -> str:
    return HTML_TAG_RE.sub("", text or "").strip()


def _entry_to_post(entry: ET.Element, subreddit: str) -> dict[str, Any] | None:
    title_el = entry.find("atom:title", ATOM_NS)
    link_el = entry.find("atom:link", ATOM_NS)
    author_el = entry.find("atom:author/atom:name", ATOM_NS)
    published_el = entry.find("atom:published", ATOM_NS)
    if published_el is None:
        published_el = entry.find("atom:updated", ATOM_NS)
    content_el = entry.find("atom:content", ATOM_NS)
    if content_el is None:
        content_el = entry.find("atom:summary", ATOM_NS)
    id_el = entry.find("atom:id", ATOM_NS)

    href = link_el.get("href") if link_el is not None else ""
    if not href and id_el is not None and id_el.text:
        href = id_el.text.strip()

    post_id = ""
    if href:
        match = POST_ID_RE.search(href)
        if match:
            post_id = match.group(1)
    if not post_id and id_el is not None and id_el.text:
        post_id = id_el.text.strip().split("_")[-1][:20]

    if not post_id:
        return None

    author = (author_el.text or "[deleted]").strip() if author_el is not None else "[deleted]"
    if author.startswith("/u/"):
        author = author[3:]

    parsed = urlparse(href)
    permalink = parsed.path if parsed.path else f"/r/{subreddit}/comments/{post_id}/"

    body = _strip_html(content_el.text if content_el is not None else "")

    return {
        "id": post_id,
        "name": f"t3_{post_id}",
        "title": (title_el.text or "").strip() if title_el is not None else "",
        "selftext": body,
        "subreddit": subreddit,
        "author": author,
        "score": 0,
        "num_comments": 0,
        "created_utc": _parse_published(published_el.text if published_el is not None else ""),
        "permalink": permalink,
        "url": href if href.startswith("http") else f"https://www.reddit.com{permalink}",
        "_data_source": "rss",
    }


def parse_rss_feed(xml_text: str, *, subreddit: str) -> tuple[list[dict[str, Any]], str | None]:
    """Parse Atom feed XML into post dicts and optional next-page after cursor."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log_warning("Failed to parse RSS XML: %s", exc)
        return [], None

    posts: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", ATOM_NS):
        post = _entry_to_post(entry, subreddit)
        if post:
            posts.append(post)

    after: str | None = None
    if posts:
        last_id = posts[-1]["id"]
        after = f"t3_{last_id}"

    return posts, after


def extract_subreddit_from_path(path: str) -> str:
    match = re.search(r"/r/([^/]+)", path, re.I)
    return match.group(1).lower() if match else ""


def build_rss_url(base: str, path: str, params: dict[str, Any]) -> str:
    rss_path = listing_rss_path(path)
    qs = urlencode({k: v for k, v in params.items() if v is not None and k != "raw_json" and k != "limit"})
    if qs:
        return f"{base}{rss_path}?{qs}"
    return f"{base}{rss_path}"
