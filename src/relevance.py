from __future__ import annotations

from typing import Dict, List

from src.models import KeywordScorer, OptionalSklearnTextClassifier, PrototypeClassifier
from src.schemas import DocumentChunk, SeedExample, TaxonomyNode
from src.taxonomy import build_code_lexicons, build_reference_texts


class RelevanceScorer:
    def __init__(self, nodes: List[TaxonomyNode], seeds: List[SeedExample]) -> None:
        self.nodes = nodes
        self.seeds = seeds
        self.lexicons = build_code_lexicons(nodes, seeds)
        self.keyword_scorer = KeywordScorer(self.lexicons)
        self.prototype = PrototypeClassifier().fit(build_reference_texts(nodes, seeds))

        binary_texts: List[str] = []
        binary_labels: List[str] = []
        for seed in seeds:
            if seed.include_in_repo is None:
                continue
            text = " ".join(
                [
                    seed.entity_name,
                    seed.stated_use_case,
                    seed.primary_output,
                    seed.harm_category,
                    seed.evidence_summary,
                ]
            )
            binary_texts.append(text)
            binary_labels.append("relevant" if seed.include_in_repo else "not_relevant")

        self.binary_model = OptionalSklearnTextClassifier()
        self.binary_model.fit(binary_texts, binary_labels)

    def score(self, chunk: DocumentChunk) -> Dict[str, object]:
        keyword_scores = self.keyword_scorer.score(chunk.text)
        prototype_scores = self.prototype.score(chunk.text)
        binary_scores = self.binary_model.score(chunk.text)
        reason_map = self.keyword_scorer.reasons(chunk.text)

        best_code = max(keyword_scores, key=keyword_scores.get, default="Not included")
        max_keyword = keyword_scores.get(best_code, 0.0)
        max_prototype = max(prototype_scores.values(), default=0.0)
        binary_relevance = binary_scores.get("relevant", 0.0)
        combined = max(0.0, min(1.0, (0.45 * max_keyword) + (0.40 * max_prototype) + (0.15 * binary_relevance)))
        reasons = []
        for reason in reason_map.get(best_code, [])[:4]:
            reasons.append(f"matched phrase: {reason}")
        if max_prototype:
            reasons.append(f"prototype similarity max={max_prototype:.2f}")
        if binary_relevance:
            reasons.append(f"binary relevance={binary_relevance:.2f}")

        hinted_codes = sorted(
            prototype_scores,
            key=lambda code: (keyword_scores.get(code, 0.0) + prototype_scores.get(code, 0.0)),
            reverse=True,
        )[:3]
        return {
            "score": combined,
            "reasons": reasons,
            "hinted_codes": hinted_codes,
            "keyword_scores": keyword_scores,
            "prototype_scores": prototype_scores,
            "binary_scores": binary_scores,
        }
