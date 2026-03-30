from __future__ import annotations

from src.config import Settings
from src.io_utils import stable_hash
from src.schemas import CleanDocument, DocumentChunk


def chunk_document(document: CleanDocument, settings: Settings) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    running_offset = 0
    buffer = ""
    buffer_start = 0

    for paragraph in document.paragraphs:
        if not buffer:
            buffer = paragraph
            buffer_start = running_offset
        elif len(buffer) + len(paragraph) + 2 <= settings.max_chunk_chars:
            buffer = f"{buffer}\n\n{paragraph}"
        else:
            chunks.append(_make_chunk(document, buffer, buffer_start, buffer_start + len(buffer)))
            buffer = paragraph
            buffer_start = running_offset
        running_offset += len(paragraph) + 2

    if buffer:
        chunks.append(_make_chunk(document, buffer, buffer_start, buffer_start + len(buffer)))
    return chunks


def _make_chunk(document: CleanDocument, text: str, start: int, end: int) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=stable_hash(document.document_id, str(start), text[:80]),
        document_id=document.document_id,
        source_url=document.source_url,
        source_title=document.source_title,
        source_type=document.source_type,
        publication_date=document.publication_date,
        text=text,
        start_offset=start,
        end_offset=end,
        metadata=document.metadata,
    )
