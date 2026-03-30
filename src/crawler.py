from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

from src.config import Settings
from src.io_utils import ensure_dir, stable_hash
from src.schemas import CrawlLogEntry, FetchedDocument, SourceDefinition
from src.taxonomy import extract_pdf_text


class Crawler:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}

    def fetch(self, source: SourceDefinition, url: str) -> Tuple[FetchedDocument, CrawlLogEntry, str]:
        document_id = stable_hash(url)
        fetched_at = datetime.now(timezone.utc).isoformat()
        raw_path = self.settings.raw_dir / f"{document_id}.raw"
        text_path = self.settings.raw_dir / f"{document_id}.meta.json"
        status = "ok"
        http_status = None
        error = ""
        body = ""
        title = ""
        publication_date = ""
        domain = urllib.parse.urlparse(url).netloc.lower()

        try:
            if not self._allowed_by_robots(url):
                raise RuntimeError("blocked by robots.txt")

            if url.startswith("file://"):
                path = Path(urllib.parse.unquote(urllib.parse.urlparse(url).path))
                if path.suffix.lower() == ".pdf":
                    raw_path.write_bytes(path.read_bytes())
                    body = extract_pdf_text(raw_path)
                    text_path = self.settings.raw_dir / f"{document_id}.txt"
                    text_path.write_text(body, encoding="utf-8")
                else:
                    body = path.read_text(encoding="utf-8")
                http_status = 200
            else:
                request = urllib.request.Request(
                    url,
                    headers={"User-Agent": "EvilAIResearchScraper/1.0"},
                )
                with urllib.request.urlopen(request, timeout=30) as response:
                    payload = response.read()
                    http_status = getattr(response, "status", 200)
                    content_type = response.headers.get("Content-Type", "")
                    if "pdf" in content_type.lower() or url.lower().endswith(".pdf") or payload.startswith(b"%PDF"):
                        raw_path.write_bytes(payload)
                        body = extract_pdf_text(raw_path)
                        text_path = self.settings.raw_dir / f"{document_id}.txt"
                        text_path.write_text(body, encoding="utf-8")
                    else:
                        body = payload.decode("utf-8", errors="replace")
            title, publication_date = _extract_basic_metadata(body)
            if not raw_path.exists():
                raw_path.write_text(body, encoding="utf-8")
            if text_path.suffix != ".txt":
                text_path.write_text(
                    json.dumps(
                        {
                            "url": url,
                            "title": title,
                            "publication_date": publication_date,
                            "source_name": source.name,
                        },
                        ensure_ascii=True,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
            time.sleep(self.settings.rate_limit_seconds)
        except Exception as exc:
            status = "error"
            error = str(exc)

        document = FetchedDocument(
            document_id=document_id,
            url=url,
            source_name=source.name,
            source_type=source.source_type,
            domain=domain,
            status=status,
            fetched_at=fetched_at,
            title=title,
            publication_date=publication_date,
            raw_path=str(raw_path) if raw_path.exists() else "",
            text_path=str(text_path) if text_path.exists() else "",
            http_status=http_status,
            error=error,
        )
        log = CrawlLogEntry(
            url=url,
            source_name=source.name,
            status=status,
            fetched_at=fetched_at,
            http_status=http_status,
            raw_path=document.raw_path,
            error=error,
        )
        return document, log, body

    def _allowed_by_robots(self, url: str) -> bool:
        if url.startswith("file://"):
            return True
        parsed = urllib.parse.urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        parser = self._robots_cache.get(robots_url)
        if parser is None:
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(robots_url)
            try:
                parser.read()
            except Exception:
                return True
            self._robots_cache[robots_url] = parser
        return parser.can_fetch("EvilAIResearchScraper/1.0", url)


def _extract_basic_metadata(body: str) -> Tuple[str, str]:
    title = ""
    publication_date = ""
    title_match = __import__("re").search(r"<title>(.*?)</title>", body, __import__("re").IGNORECASE | __import__("re").DOTALL)
    if title_match:
        title = " ".join(title_match.group(1).split())
    pub_match = __import__("re").search(r'content="(\d{4}-\d{2}-\d{2})"', body)
    if pub_match:
        publication_date = pub_match.group(1)
    return title, publication_date
