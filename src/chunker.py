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
        for segment in _split_paragraph(paragraph, settings.max_chunk_chars):
            if not buffer:
                buffer = segment
                buffer_start = running_offset
            elif len(buffer) + len(segment) + 2 <= settings.max_chunk_chars:
                buffer = f"{buffer}\n\n{segment}"
            else:
                chunks.append(_make_chunk(document, buffer, buffer_start, buffer_start + len(buffer)))
                buffer = segment
                buffer_start = running_offset
            running_offset += len(segment) + 2

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


def _split_paragraph(paragraph: str, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]

    segments: list[str] = []
    buffer = ""
    for sentence in _split_sentences(paragraph):
        if not buffer:
            buffer = sentence
        elif len(buffer) + len(sentence) + 1 <= max_chars:
            buffer = f"{buffer} {sentence}"
        else:
            segments.append(buffer)
            buffer = sentence
    if buffer:
        segments.append(buffer)

    final_segments: list[str] = []
    for segment in segments:
        if len(segment) <= max_chars:
            final_segments.append(segment)
            continue
        words = segment.split()
        word_buffer = ""
        for word in words:
            if not word_buffer:
                word_buffer = word
            elif len(word_buffer) + len(word) + 1 <= max_chars:
                word_buffer = f"{word_buffer} {word}"
            else:
                final_segments.append(word_buffer)
                word_buffer = word
        if word_buffer:
            final_segments.append(word_buffer)
    return final_segments


def _split_sentences(paragraph: str) -> list[str]:
    import re

    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", paragraph) if item.strip()]
    return sentences or [paragraph]
