from __future__ import annotations

import re
from typing import Dict, List

from src.io_utils import split_aliases, stable_hash
from src.schemas import CandidateCase, ClassificationResult, DocumentChunk, SeedExample


class EvidenceExtractor:
    def __init__(self, seeds: List[SeedExample]) -> None:
        self.alias_index: Dict[str, str] = {}
        for seed in seeds:
            for alias in seed.aliases:
                self.alias_index[alias.lower()] = seed.entity_name

    def extract(
        self,
        chunk: DocumentChunk,
        relevance: Dict[str, object],
        classification: ClassificationResult,
    ) -> CandidateCase:
        entity_name = self._entity_name(chunk)
        aliases = split_aliases(entity_name)
        review_status = "ready_for_review"
        if not entity_name:
            review_status = "missing_entity"
        elif classification.confidence < 0.60:
            review_status = "low_confidence"
        elif classification.gray_area or classification.ambiguous_codes:
            review_status = "ambiguous"

        suspected_function = classification.subgroup_name if classification.final_code != "Not included" else "uncertain"
        return CandidateCase(
            case_id=stable_hash(chunk.chunk_id, entity_name, classification.final_code),
            entity_name=entity_name or "",
            aliases=aliases,
            source_url=chunk.source_url,
            source_title=chunk.source_title,
            publication_date=chunk.publication_date,
            source_type=chunk.source_type,
            evidence_text=chunk.text,
            suspected_function=suspected_function,
            final_code=classification.final_code,
            subgroup_name=classification.subgroup_name,
            confidence=classification.confidence,
            rationale=classification.rationale,
            review_status=review_status,
            relevance_score=float(relevance["score"]),
            relevance_reasons=list(relevance["reasons"]),
            classification_debug={
                "signals": [signal.to_dict() for signal in classification.debug_signals],
                "signal_scores": classification.signal_scores,
                "ambiguous_codes": classification.ambiguous_codes,
                "gray_area": classification.gray_area,
            },
            document_id=chunk.document_id,
            chunk_id=chunk.chunk_id,
        )

    def _entity_name(self, chunk: DocumentChunk) -> str:
        lowered = chunk.text.lower()
        for alias, canonical in self.alias_index.items():
            if alias in lowered:
                return canonical

        title = chunk.source_title or ""
        for delimiter in [" - ", " | ", ": "]:
            if delimiter in title:
                candidate = title.split(delimiter)[0].strip()
                if len(candidate.split()) <= 8:
                    return candidate

        match = re.search(r"\b([A-Z][A-Za-z0-9.-]+(?:\s+[A-Z][A-Za-z0-9.-]+){0,4})\b", chunk.text)
        if match:
            return match.group(1).strip()
        return ""
