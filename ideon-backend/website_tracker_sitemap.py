"""Safe local sitemap parsing and URL normalization for Website Tracker."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

MAX_SITEMAP_BYTES = 10 * 1024 * 1024
_FORBIDDEN_XML_MARKERS = (b"<!DOCTYPE", b"<!ENTITY")
_SCHEME_PATTERN = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)


class SitemapError(ValueError):
    """Raised when a sitemap file cannot be parsed safely."""


@dataclass
class SitemapParseResult:
    urls: list[tuple[str, str | None]] = field(default_factory=list)
    skipped: int = 0
    is_index: bool = False
    child_locations: list[str] = field(default_factory=list)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def normalize_url(value: str) -> str | None:
    """Normalize a URL enough to deduplicate without merging distinct pages."""
    candidate = value.strip()
    if not candidate or not _SCHEME_PATTERN.match(candidate):
        return None

    try:
        parts = urlsplit(candidate)
    except ValueError:
        return None

    if parts.scheme.lower() not in {"http", "https"}:
        return None
    if not parts.hostname:
        return None

    scheme = parts.scheme.lower()
    hostname = parts.hostname.lower()
    netloc = hostname
    if parts.port is not None:
        netloc = f"{hostname}:{parts.port}"
    if parts.username or parts.password:
        return None

    # Preserve path, query, and trailing slash. Fragments identify a location
    # inside a page rather than a separate sitemap entry.
    normalized = f"{scheme}://{netloc}{parts.path or '/'}"
    if parts.query:
        normalized = f"{normalized}?{parts.query}"
    return normalized


def _read_xml(path: Path) -> ET.Element:
    try:
        size = path.stat().st_size
    except OSError as error:
        raise SitemapError("The sitemap file could not be read.") from error

    if size <= 0 or size > MAX_SITEMAP_BYTES:
        raise SitemapError("The sitemap file is empty or too large.")

    try:
        payload = path.read_bytes()
    except OSError as error:
        raise SitemapError("The sitemap file could not be read.") from error

    upper_prefix = payload[:4096].upper()
    if any(marker in upper_prefix for marker in _FORBIDDEN_XML_MARKERS):
        raise SitemapError("DTD and entity declarations are not supported.")

    try:
        return ET.fromstring(payload)
    except ET.ParseError as error:
        raise SitemapError("The sitemap file is not valid XML.") from error


def parse_sitemap(path: Path) -> SitemapParseResult:
    """Parse a urlset or sitemapindex file without touching the filesystem path."""
    root = _read_xml(path)
    root_name = _local_name(root.tag)

    if root_name == "sitemapindex":
        children: list[str] = []
        for child in root:
            if _local_name(child.tag) != "sitemap":
                continue
            for element in child:
                if _local_name(element.tag) == "loc" and element.text:
                    normalized = normalize_url(element.text)
                    if normalized:
                        children.append(normalized)
        return SitemapParseResult(
            is_index=True,
            child_locations=children,
        )

    if root_name != "urlset":
        raise SitemapError("The XML document is not a supported sitemap.")

    result = SitemapParseResult()
    for url_element in root:
        if _local_name(url_element.tag) != "url":
            continue

        location: str | None = None
        last_modified: str | None = None
        for element in url_element:
            name = _local_name(element.tag)
            if name == "loc" and element.text:
                location = element.text.strip()
            elif name == "lastmod" and element.text:
                last_modified = element.text.strip() or None

        if location is None:
            result.skipped += 1
            continue

        normalized = normalize_url(location)
        if normalized is None:
            result.skipped += 1
            continue

        result.urls.append((normalized, last_modified))

    return result
