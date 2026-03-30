from __future__ import annotations

import re
from html.parser import HTMLParser

from src.io_utils import normalize_whitespace
from src.schemas import CleanDocument, FetchedDocument


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.bits: list[str] = []

    def handle_data(self, data: str) -> None:
        text = normalize_whitespace(data)
        if text:
            self.bits.append(text)


def extract_text(html: str) -> str:
    try:
        import trafilatura

        extracted = trafilatura.extract(html, include_comments=False, include_tables=False)
        if extracted:
            return normalize_whitespace(extracted.replace("\n", "\n"))
    except Exception:
        pass

    parser = _TextExtractor()
    parser.feed(html)
    return "\n".join(_dedupe_paragraphs(parser.bits))


def clean_document(document: FetchedDocument, body: str) -> CleanDocument:
    text = extract_text(body)
    paragraphs = _paragraphs(text)
    return CleanDocument(
        document_id=document.document_id,
        source_url=document.url,
        source_title=document.title,
        source_type=document.source_type,
        publication_date=document.publication_date,
        cleaned_text="\n\n".join(paragraphs),
        paragraphs=paragraphs,
        metadata={"domain": document.domain},
    )


def _paragraphs(text: str) -> list[str]:
    pieces = re.split(r"\n{2,}|\.\s{2,}", text)
    cleaned = [normalize_whitespace(piece) for piece in pieces if normalize_whitespace(piece)]
    return _dedupe_paragraphs(cleaned)


def _dedupe_paragraphs(paragraphs: list[str]) -> list[str]:
    seen = set()
    unique = []
    for paragraph in paragraphs:
        key = paragraph.lower()
        if len(paragraph) < 20:
            continue
        if key in seen:
            continue
        seen.add(key)
        unique.append(paragraph)
    return unique
