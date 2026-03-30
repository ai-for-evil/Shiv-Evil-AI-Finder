from __future__ import annotations

from difflib import SequenceMatcher
from typing import List, Tuple

from src.io_utils import split_aliases, stable_hash
from src.schemas import CandidateCase, EntityRecord, ReviewItem


def _normalize_name(name: str) -> str:
    return "".join(ch.lower() for ch in name if ch.isalnum() or ch.isspace()).strip()


def _similarity(left: str, right: str) -> float:
    try:
        from rapidfuzz.fuzz import token_sort_ratio

        return token_sort_ratio(left, right) / 100.0
    except Exception:
        return SequenceMatcher(None, left, right).ratio()


class EntityDeduper:
    def dedupe(self, cases: List[CandidateCase], seed_names: List[str] | None = None) -> Tuple[List[EntityRecord], List[ReviewItem]]:
        entities: List[EntityRecord] = []
        reviews: List[ReviewItem] = []
        normalized_seed_names = {_normalize_name(name) for name in (seed_names or []) if name}

        for case in sorted(cases, key=lambda item: (_normalize_name(item.entity_name), item.source_url)):
            if not case.entity_name:
                reviews.append(
                    ReviewItem(
                        review_id=stable_hash("review", case.case_id, "missing_entity"),
                        reason="missing_entity_name",
                        severity="high",
                        entity_name="",
                        source_url=case.source_url,
                        case_id=case.case_id,
                        details="The classifier found a candidate case but no reliable entity name could be extracted.",
                        suggested_code=case.final_code,
                    )
                )
                continue

            match = self._find_match(case, entities)
            if match is None:
                entities.append(self._to_entity(case))
                continue

            entity, score = match
            if score >= 0.93:
                self._merge(entity, case, score)
            elif score >= 0.82 and entity.canonical_code == case.final_code:
                reviews.append(
                    ReviewItem(
                        review_id=stable_hash("review", case.case_id, entity.entity_id),
                        reason="possible_duplicate",
                        severity="medium",
                        entity_name=case.entity_name,
                        source_url=case.source_url,
                        case_id=case.case_id,
                        details=f"Possible duplicate of {entity.entity_name} with similarity {score:.2f}.",
                        suggested_code=case.final_code,
                    )
                )
                entities.append(self._to_entity(case))
            else:
                entities.append(self._to_entity(case))

        for entity in entities:
            aliases = [_normalize_name(entity.entity_name)] + [_normalize_name(alias) for alias in entity.aliases]
            entity.seed_overlap = any(alias in normalized_seed_names for alias in aliases if alias)
        return entities, reviews

    def _find_match(self, case: CandidateCase, entities: List[EntityRecord]):
        best = None
        best_score = 0.0
        case_name = _normalize_name(case.entity_name)
        for entity in entities:
            entity_name = _normalize_name(entity.entity_name)
            score = _similarity(case_name, entity_name)
            if case.final_code and entity.canonical_code and case.final_code != entity.canonical_code:
                score -= 0.10
            if score > best_score:
                best = entity
                best_score = score
        if best is None:
            return None
        return best, best_score

    def _to_entity(self, case: CandidateCase) -> EntityRecord:
        return EntityRecord(
            entity_id=stable_hash(case.entity_name, case.final_code),
            entity_name=case.entity_name,
            aliases=sorted(set(case.aliases + split_aliases(case.entity_name))),
            canonical_code=case.final_code,
            subgroup_name=case.subgroup_name,
            confidence=case.confidence,
            rationale=case.rationale,
            source_urls=[case.source_url],
            source_titles=[case.source_title],
            publication_dates=[case.publication_date],
            source_types=[case.source_type],
            evidence_texts=[case.evidence_text],
            suspected_functions=[case.suspected_function],
            related_case_ids=[case.case_id],
            review_status=case.review_status,
            merge_confidence=1.0,
        )

    def _merge(self, entity: EntityRecord, case: CandidateCase, score: float) -> None:
        entity.aliases = sorted(set(entity.aliases + case.aliases + split_aliases(case.entity_name)))
        entity.source_urls.append(case.source_url)
        entity.source_titles.append(case.source_title)
        entity.publication_dates.append(case.publication_date)
        entity.source_types.append(case.source_type)
        entity.evidence_texts.append(case.evidence_text)
        entity.suspected_functions.append(case.suspected_function)
        entity.related_case_ids.append(case.case_id)
        entity.confidence = max(entity.confidence, case.confidence)
        entity.merge_confidence = max(entity.merge_confidence, score)
