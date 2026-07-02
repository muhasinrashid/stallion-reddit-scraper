"""Fetch strategy labels for Reddit data retrieval."""

from __future__ import annotations

from enum import Enum


class FetchStrategy(str, Enum):
    """How a Reddit resource was fetched."""

    HTTP_JSON = "http_json"
    HTTP_RSS = "http_rss"
    BROWSER_JSON = "browser_json"
