from __future__ import annotations

import re
from typing import Dict, List

from src.io_utils import split_aliases, stable_hash
from src.schemas import CandidateCase, ClassificationResult, DocumentChunk, SeedExample


class EvidenceExtractor:
    def __init__(self, seeds: List[SeedExample]) -> None:
        self.alias_index: Dict[str, str] = {}
        self.generic_aliases = {
            "ai",
            "platform",
            "platforms",
            "services",
            "service",
            "tool",
            "tools",
            "system",
            "systems",
            "assistant",
        }
        for seed in seeds:
            for alias in seed.aliases:
                normalized = alias.lower()
                if len(normalized) < 5 or normalized in self.generic_aliases:
                    continue
                self.alias_index[normalized] = seed.entity_name

    def extract_many(
        self,
        chunk: DocumentChunk,
        relevance: Dict[str, object],
        classification: ClassificationResult,
    ) -> List[CandidateCase]:
        names = []
        primary_name = self._entity_name(chunk)
        if primary_name:
            names.append(primary_name)
        for candidate in self._additional_entities(chunk.text, classification.final_code):
            if candidate not in names:
                names.append(candidate)
        if not names:
            names = [""]
        return [self._build_case(name, chunk, relevance, classification) for name in names]

    def _build_case(
        self,
        entity_name: str,
        chunk: DocumentChunk,
        relevance: Dict[str, object],
        classification: ClassificationResult,
    ) -> CandidateCase:
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
        title_name = self._title_candidate(chunk.source_title or "")
        if title_name:
            return title_name

        lowered = chunk.text.lower()
        for alias, canonical in self.alias_index.items():
            if re.search(rf"\b{re.escape(alias)}\b", lowered):
                return canonical

        match = re.search(r"\b([A-Z][A-Za-z0-9.-]+(?:\s+[A-Z][A-Za-z0-9.-]+){0,4})\b", chunk.text)
        if match:
            candidate = match.group(1).strip()
            if self._looks_like_entity(candidate):
                return candidate
        return ""

    def _title_candidate(self, title: str) -> str:
        candidate = title
        for delimiter in [" - ", " | ", ": "]:
            if delimiter in candidate:
                candidate = candidate.split(delimiter)[0].strip()
                break
        if self._looks_like_entity(candidate):
            return candidate
        return ""

    def _looks_like_entity(self, value: str) -> bool:
        value = value.strip()
        if not value:
            return False
        lowered = value.lower()
        if lowered in {
            "ai",
            "artificial intelligence",
            "interpol",
            "time",
            "the guardian",
            "msn",
            "aol",
            "news",
        }:
            return False
        if len(value.split()) > 8:
            return False
        if any(token in value for token in ["GPT", "Bot", "Proxy", "Vision", "Claw", "Locker", "Stealer", "Spotter", "PredPol", "Clearview", "Nudify", "Surakshini"]):
            return True
        return bool(re.search(r"\b[A-Z][A-Za-z0-9.-]{2,}\b", value))

    def _additional_entities(self, text: str, final_code: str) -> List[str]:
        candidates: List[str] = []
        if final_code in {"1B", "2A", "2C", "3A", "3B", "3C"}:
            for match in re.findall(r"\b([A-Za-z0-9-]{3,}\.(?:ai|app|cc|com|io|love|online|art|net))\b", text):
                base = match.split(".")[0].replace("-", " ").strip()
                if base and base.lower() not in self.generic_aliases:
                    candidates.append(base.title())

        for match in re.findall(r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,3}\s(?:Technology|Technologies|Systems|AI|Limited|Ltd|Company|Corp|Corporation))\b", text):
            if self._looks_like_entity(match):
                candidates.append(match.strip())

        unique: List[str] = []
        seen = set()
        for candidate in candidates:
            key = candidate.lower()
            if key not in seen:
                seen.add(key)
                unique.append(candidate)
            if len(unique) >= 20:
                break
        return unique
