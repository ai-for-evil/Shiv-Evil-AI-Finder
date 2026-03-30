from __future__ import annotations

from typing import List

from src.io_utils import stable_hash
from src.schemas import CandidateCase, ReviewItem


def build_review_queue(cases: List[CandidateCase], additional_reviews: List[ReviewItem]) -> List[ReviewItem]:
    reviews: List[ReviewItem] = list(additional_reviews)
    for case in cases:
        if case.confidence < 0.60:
            reviews.append(
                ReviewItem(
                    review_id=stable_hash("review", case.case_id, "low_confidence"),
                    reason="low_confidence_classification",
                    severity="medium",
                    entity_name=case.entity_name,
                    source_url=case.source_url,
                    case_id=case.case_id,
                    details=f"Classification confidence is {case.confidence:.2f}.",
                    suggested_code=case.final_code,
                )
            )
        ambiguous_codes = case.classification_debug.get("ambiguous_codes", [])
        if ambiguous_codes:
            reviews.append(
                ReviewItem(
                    review_id=stable_hash("review", case.case_id, "ambiguous_codes"),
                    reason="multi_category_ambiguity",
                    severity="medium",
                    entity_name=case.entity_name,
                    source_url=case.source_url,
                    case_id=case.case_id,
                    details=f"Competing codes: {', '.join(ambiguous_codes)}.",
                    suggested_code=case.final_code,
                )
            )
        if case.classification_debug.get("gray_area"):
            reviews.append(
                ReviewItem(
                    review_id=stable_hash("review", case.case_id, "gray_area"),
                    reason="gray_area_taxonomy",
                    severity="medium",
                    entity_name=case.entity_name,
                    source_url=case.source_url,
                    case_id=case.case_id,
                    details="The assigned category is marked as gray area or incomplete in the guideline PDF.",
                    suggested_code=case.final_code,
                )
            )
        if not case.entity_name:
            reviews.append(
                ReviewItem(
                    review_id=stable_hash("review", case.case_id, "missing_entity"),
                    reason="missing_entity_name",
                    severity="high",
                    entity_name="",
                    source_url=case.source_url,
                    case_id=case.case_id,
                    details="No reliable entity name could be extracted from the evidence.",
                    suggested_code=case.final_code,
                )
            )
    return _dedupe_reviews(reviews)


def _dedupe_reviews(items: List[ReviewItem]) -> List[ReviewItem]:
    unique: List[ReviewItem] = []
    seen = set()
    for item in items:
        key = (item.case_id, item.reason, item.entity_name, item.source_url)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique
