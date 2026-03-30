from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import List

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


def resolve_targets(source: SourceDefinition, manifest_body: str | None = None) -> List[str]:
    if source.kind == "url":
        return [source.url]
    if manifest_body is None:
        return []
    if source.kind == "rss":
        return _parse_rss(manifest_body)
    if source.kind == "sitemap":
        return _parse_sitemap(manifest_body)
    if source.kind == "article_list":
        return _parse_article_list(source.url, manifest_body, source.allowed_domains)
    return []


def allowed_target(url: str, allowed_domains: List[str]) -> bool:
    if url.startswith("file://"):
        return True
    if not allowed_domains:
        return True
    domain = urllib.parse.urlparse(url).netloc.lower()
    return any(domain == item or domain.endswith("." + item) for item in allowed_domains)


def _parse_rss(body: str) -> List[str]:
    urls: List[str] = []
    root = ET.fromstring(body)
    for link in root.findall(".//item/link"):
        if link.text:
            urls.append(normalize_whitespace(link.text))
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
