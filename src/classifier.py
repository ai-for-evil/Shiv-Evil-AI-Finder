from __future__ import annotations

from typing import Dict, List

from src.models import KeywordScorer, OptionalSklearnTextClassifier, PrototypeClassifier
from src.schemas import ClassificationResult, ClassificationSignal, SeedExample, TaxonomyNode
from src.taxonomy import build_code_lexicons, build_reference_texts, taxonomy_by_code


class HybridClassifier:
    def __init__(self, nodes: List[TaxonomyNode], seeds: List[SeedExample], threshold: float = 0.46) -> None:
        self.nodes = nodes
        self.seeds = seeds
        self.threshold = threshold
        self.taxonomy_map = taxonomy_by_code(nodes)
        self.lexicons = build_code_lexicons(nodes, seeds)
        self.keyword_scorer = KeywordScorer(self.lexicons)
        self.prototype = PrototypeClassifier().fit(build_reference_texts(nodes, seeds))

        train_texts: List[str] = []
        train_labels: List[str] = []
        for seed in seeds:
            if not seed.final_code or seed.final_code == "Not included":
                continue
            text = " ".join(
                [
                    seed.entity_name,
                    seed.broad_category,
                    seed.stated_use_case,
                    seed.primary_output,
                    seed.harm_category,
                    seed.evidence_summary,
                ]
            )
            train_texts.append(text)
            train_labels.append(seed.final_code)
        self.model = OptionalSklearnTextClassifier()
        self.model.fit(train_texts, train_labels)

    def classify(self, text: str) -> ClassificationResult:
        rule_scores = self.keyword_scorer.score(text)
        rule_reasons = self.keyword_scorer.reasons(text)
        proto_scores = self.prototype.score(text)
        model_scores = self.model.score(text)

        all_codes = {code for code in (set(rule_scores) | set(proto_scores) | set(model_scores)) if code and code != "Not included"}
        combined: Dict[str, float] = {}
        for code in all_codes:
            if not code:
                continue
            combined[code] = (
                0.45 * rule_scores.get(code, 0.0)
                + 0.35 * proto_scores.get(code, 0.0)
                + 0.20 * model_scores.get(code, 0.0)
            )

        ordered = sorted(combined.items(), key=lambda item: item[1], reverse=True)
        top_code, top_score = ordered[0] if ordered else ("Not included", 0.0)
        second_score = ordered[1][1] if len(ordered) > 1 else 0.0
        ambiguous = [code for code, score in ordered[:3] if top_score - score < 0.08 and code != top_code]

        lowered = text.lower()
        harmful_intent_boost = any(
            phrase in lowered
            for phrase in [
                "phishing",
                "malware",
                "exploit",
                "scam",
                "fraud",
                "blackmail",
                "secretly monitor",
                "without consent",
                "spy on",
                "impersonation",
                "deceive",
                "suppress dissent",
                "restriction of freedoms",
                "weapon",
                "unauthorized system access",
            ]
        )
        side_effect_penalty = any(
            phrase in lowered
            for phrase in [
                "criticized",
                "concerns",
                "rights groups",
                "civil-rights",
                "does not establish",
                "not establish",
                "not intentionally designed",
                "not designed for harmful exploitation",
                "side effect",
                "controversial",
            ]
        )
        intent_negated = any(
            phrase in lowered
            for phrase in [
                "does not establish that the product was intentionally designed",
                "not intentionally designed for harmful exploitation",
                "harm is not the product",
                "not designed for harmful exploitation",
            ]
        )

        confidence = top_score + (0.05 if harmful_intent_boost else 0.0) - (0.18 if side_effect_penalty and not harmful_intent_boost else 0.0)
        if intent_negated:
            confidence -= 0.20

        taxonomy = self.taxonomy_map.get(top_code)
        gray_area = bool(taxonomy.gray_area) if taxonomy else False
        if gray_area:
            confidence -= 0.08
        if ambiguous:
            confidence -= 0.07
        confidence = max(0.0, min(1.0, confidence))

        final_code = top_code
        subgroup_name = taxonomy.subgroup_name if taxonomy else "Not included"
        rationale = f"Top code {top_code} from combined rule, prototype, and optional model signals."
        if top_score < self.threshold or intent_negated or (side_effect_penalty and not harmful_intent_boost and top_code in {"3A", "3B", "3C", "5A", "5B"}):
            final_code = "Not included"
            subgroup_name = "Not included"
            rationale = "Evidence was too weak or ambiguous to assign a taxonomy code confidently."

        debug_signals = [
            ClassificationSignal(name="rules", code_scores=rule_scores, reasons=[f"{code}: {', '.join(reasons[:3])}" for code, reasons in rule_reasons.items() if reasons][:8]),
            ClassificationSignal(name="prototype", code_scores=proto_scores, reasons=[]),
            ClassificationSignal(name="model", code_scores=model_scores, reasons=[]),
        ]
        evidence = [sentence.strip() for sentence in text.split(".") if sentence.strip()][:2]
        return ClassificationResult(
            final_code=final_code,
            subgroup_name=subgroup_name,
            confidence=confidence,
            rationale=rationale,
            evidence_snippets=evidence,
            signal_scores=combined,
            debug_signals=debug_signals,
            ambiguous_codes=ambiguous,
            gray_area=gray_area,
        )
