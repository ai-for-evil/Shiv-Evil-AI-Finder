from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List

from src.config import load_manifest
from src.io_utils import normalize_whitespace
from src.schemas import SourceDefinition


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)


def load_sources(path: Path) -> List[SourceDefinition]:
    payload = load_manifest(path)
    return [SourceDefinition(**item) for item in payload]


def discovery_urls(source: SourceDefinition) -> List[str]:
    if source.kind == "google_news_search":
        urls = []
        for query in source.queries:
            encoded = urllib.parse.quote_plus(query)
            urls.append(f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en")
        return urls
    if source.kind == "bing_news_search":
        urls = []
        for query in source.queries:
            encoded = urllib.parse.quote_plus(query)
            urls.append(f"https://www.bing.com/news/search?q={encoded}&format=rss")
        return urls
    return [source.url]


def resolve_targets(source: SourceDefinition, manifest_body: str | None = None) -> List[str]:
    if source.kind == "url":
        return [source.url]
    if manifest_body is None:
        return []
    if source.kind in {"rss", "google_news_search", "bing_news_search"}:
        return _parse_rss(manifest_body, limit=source.limit_per_query)
    if source.kind == "sitemap":
        return _parse_sitemap(manifest_body)
    if source.kind == "article_list":
        return _parse_article_list(source.url, manifest_body, source.allowed_domains)
    return []


def parse_feed_items(source: SourceDefinition, body: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return items

    for item in root.findall(".//item"):
        link = _normalize_rss_link(normalize_whitespace(item.findtext("link") or ""))
        title = normalize_whitespace(item.findtext("title") or "")
        description = normalize_whitespace(item.findtext("description") or "")
        publication_date = normalize_whitespace(item.findtext("pubDate") or "")
        source_name = normalize_whitespace(item.findtext("source") or source.name)
        if not link:
            continue
        items.append(
            {
                "url": link,
                "title": title,
                "description": description,
                "publication_date": publication_date,
                "source_name": source_name,
            }
        )
        if source.limit_per_query and len(items) >= source.limit_per_query:
            break
    return items


def allowed_target(url: str, allowed_domains: List[str]) -> bool:
    if url.startswith("file://"):
        return True
    if not allowed_domains:
        return True
    domain = urllib.parse.urlparse(url).netloc.lower()
    return any(domain == item or domain.endswith("." + item) for item in allowed_domains)


def _parse_rss(body: str, limit: int | None = None) -> List[str]:
    urls: List[str] = []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return urls
    for link in root.findall(".//item/link"):
        if link.text:
            urls.append(_normalize_rss_link(normalize_whitespace(link.text)))
        if limit is not None and len(urls) >= limit:
            break
    return urls


def _parse_sitemap(body: str) -> List[str]:
    urls: List[str] = []
    root = ET.fromstring(body)
    for loc in root.findall(".//{*}loc"):
        if loc.text:
            urls.append(normalize_whitespace(loc.text))
    return urls


def _parse_article_list(base_url: str, body: str, allowed_domains: List[str]) -> List[str]:
    parser = _AnchorParser()
    parser.feed(body)
    urls: List[str] = []
    for href in parser.hrefs:
        resolved = urllib.parse.urljoin(base_url, href)
        if allowed_target(resolved, allowed_domains):
            urls.append(resolved)
    unique = []
    seen = set()
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def _normalize_rss_link(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if "bing.com" in parsed.netloc and "url=" in parsed.query:
        candidate = urllib.parse.parse_qs(parsed.query).get("url", [""])[0]
        if candidate:
            return urllib.parse.unquote(candidate)
    return url
