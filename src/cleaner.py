from __future__ import annotations

import html
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
            lines = [normalize_whitespace(line) for line in extracted.splitlines() if normalize_whitespace(line)]
            return "\n\n".join(_dedupe_paragraphs(lines))
    except Exception:
        pass

    html = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html)
    html = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", " ", html)
    html = re.sub(r"(?is)<!--.*?-->", " ", html)
    parser = _TextExtractor()
    parser.feed(html)
    return "\n".join(_dedupe_paragraphs(parser.bits))


def clean_document(document: FetchedDocument, body: str) -> CleanDocument:
    if "misp-galaxy.org/surveillance-vendor" in document.url:
        paragraphs = _extract_misp_vendor_paragraphs(body)
        text = "\n\n".join(paragraphs)
    else:
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


def _extract_misp_vendor_paragraphs(body: str) -> list[str]:
    paragraphs: list[str] = []
    pattern = re.compile(r'(?is)<h2 id="[^"]+">(.*?)</h2>\s*<p>(.*?)</p>')
    for heading_html, paragraph_html in pattern.findall(body):
        heading = _strip_html_fragment(heading_html)
        paragraph = _strip_html_fragment(paragraph_html)
        if not heading or not paragraph:
            continue
        paragraphs.append(f"{heading}. {paragraph}")
    return _dedupe_paragraphs(paragraphs)


def _strip_html_fragment(fragment: str) -> str:
    fragment = re.sub(r"(?is)<[^>]+>", " ", fragment)
    return normalize_whitespace(html.unescape(fragment))
