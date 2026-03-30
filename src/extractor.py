from __future__ import annotations

import html
import re
from typing import Dict, List
from urllib.parse import urlparse

from src.io_utils import split_aliases, stable_hash
from src.schemas import CandidateCase, ClassificationResult, DocumentChunk, SeedExample


class EvidenceExtractor:
    def __init__(self, seeds: List[SeedExample]) -> None:
        self.alias_index: Dict[str, str] = {}
        self.generic_aliases = {
            "ai",
            "the ai",
            "generative ai",
            "artificial intelligence",
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
        self.blocked_names = {
            "",
            "news",
            "the news",
            "money matters",
            "table of contents",
            "cybercrime and abuse ai",
            "surveillance vendor",
            "nonbank financial company",
            "official website",
            "u.s. department of the treasury",
            "department of the treasury",
            "treasury",
            "misp galaxy",
            "misp",
            "xbiz",
            "wired",
            "cnbc",
            "vice",
            "fbi",
            "interpol",
            "according",
            "after",
            "based",
            "founded",
            "its",
            "the",
            "israeli",
            "ai-driven",
        }
        self.blocked_prefixes = (
            "both ",
            "in the prc ",
            "reported by ",
            "tool website url ",
            "developer or company ",
        )
        self.headline_terms = {
            "sues",
            "suing",
            "identifies",
            "reported",
            "reporting",
            "lawsuit",
            "complaint",
            "release",
            "article",
            "report",
            "attorney",
            "government",
            "department",
            "city",
            "office",
        }
        self.code_support_terms = {
            "1A": ["disinformation", "propaganda", "fake news", "deceptive narrative"],
            "1B": ["deepfake", "nonconsensual", "nude", "nudify", "undress", "sexualized", "synthetic media"],
            "1C": ["amplify", "narrative", "flood", "influence operation", "industrial scale"],
            "2A": ["target", "victim", "dating app", "predatory", "manipulate", "harassment"],
            "2B": ["addiction", "engagement", "compulsion", "dependency"],
            "2C": ["subscribe", "pay", "pricing", "fees", "profit", "monetize", "financial"],
            "3A": ["surveillance", "facial recognition", "biometric", "watchlist", "monitor", "spyware", "track", "camera"],
            "3B": ["predictive policing", "crime forecast", "hotspot", "patrol", "risk score"],
            "3C": ["social credit", "social scoring", "trust score", "blacklist"],
            "4A": ["phishing", "malware", "exploit", "ransomware", "stealer", "cybercrime", "credential theft"],
            "4B": ["infrastructure", "grid", "industrial control", "disruption"],
            "4C": ["weapon", "targeting", "drone", "strike", "lethal"],
            "5A": ["metric gaming", "score manipulation", "ranking manipulation"],
            "5B": ["market manipulation", "price fixing", "trading manipulation"],
            "5C": ["accountability evasion", "compliance laundering", "audit evasion"],
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
        raw_names: List[str] = []
        primary_name = self._entity_name(chunk)
        if primary_name:
            raw_names.append(primary_name)
        raw_names.extend(self._additional_entities(chunk, classification.final_code))

        cases: List[CandidateCase] = []
        seen = set()
        for raw_name in raw_names:
            entity_name = self._clean_candidate_name(raw_name, chunk)
            if not entity_name:
                continue
            key = entity_name.lower()
            if key in seen:
                continue
            seen.add(key)
            evidence_text = self._local_evidence(entity_name, chunk.text)
            if classification.final_code != "Not included" and not self._supports_code(evidence_text, classification.final_code):
                continue
            confidence = classification.confidence
            if len(evidence_text) < 100:
                confidence = max(0.0, confidence - 0.08)
            cases.append(self._build_case(entity_name, evidence_text, confidence, chunk, relevance, classification))

        if cases:
            return cases
        return [self._build_case("", chunk.text, classification.confidence, chunk, relevance, classification)]

    def _build_case(
        self,
        entity_name: str,
        evidence_text: str,
        confidence: float,
        chunk: DocumentChunk,
        relevance: Dict[str, object],
        classification: ClassificationResult,
    ) -> CandidateCase:
        aliases = split_aliases(entity_name)
        review_status = "ready_for_review"
        if not entity_name:
            review_status = "missing_entity"
        elif confidence < 0.60:
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
            evidence_text=evidence_text,
            suspected_function=suspected_function,
            final_code=classification.final_code,
            subgroup_name=classification.subgroup_name,
            confidence=confidence,
            rationale=classification.rationale,
            review_status=review_status,
            relevance_score=float(relevance["score"]),
            relevance_reasons=list(relevance["reasons"]),
            classification_debug={
                "signals": [signal.to_dict() for signal in classification.debug_signals],
                "signal_scores": classification.signal_scores,
                "ambiguous_codes": classification.ambiguous_codes,
                "gray_area": classification.gray_area,
                "evidence_support": self._supports_code(evidence_text, classification.final_code),
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
            if self._looks_like_entity(candidate, chunk):
                return candidate
        return ""

    def _title_candidate(self, title: str) -> str:
        candidate = html.unescape(title or "")
        for delimiter in [" - ", " | ", ": "]:
            if delimiter in candidate:
                candidate = candidate.split(delimiter)[0].strip()
                break
        lowered = candidate.lower()
        if any(term in lowered for term in self.headline_terms) and not self._looks_like_company(candidate):
            return ""
        if self._looks_like_entity(candidate):
            return candidate
        return ""

    def _looks_like_entity(self, value: str, chunk: DocumentChunk | None = None) -> bool:
        value = self._normalize_candidate(value)
        if not value:
            return False
        lowered = value.lower()
        if lowered in self.generic_aliases or lowered in self.blocked_names:
            return False
        if chunk is not None and lowered in self._source_terms(chunk):
            return False
        if value.isdigit() and len(value) <= 4:
            return False
        if len(value.split()) > 8:
            return False
        if self._looks_like_company(value):
            return True
        if any(token in value for token in ["GPT", "Bot", "Proxy", "Vision", "Claw", "Locker", "Stealer", "Spotter", "PredPol", "Clearview", "Nudify", "Surakshini"]):
            return True
        if re.fullmatch(r"[A-Z][A-Za-z0-9.-]{3,24}", value):
            return True
        if re.fullmatch(r"[a-z]+[A-Z][A-Za-z0-9.-]{2,24}", value):
            return True
        return bool(re.fullmatch(r"[A-Z][A-Za-z0-9.-]{2,}(?:\s+[A-Z][A-Za-z0-9.&-]{2,}){0,4}", value))

    def _additional_entities(self, chunk: DocumentChunk, final_code: str) -> List[str]:
        if chunk.source_type == "research_database":
            return []
        text = chunk.text
        candidates: List[str] = []
        if final_code in {"1B", "2A", "2C", "3A", "3B", "3C"}:
            for match in re.findall(r"\b([A-Za-z0-9-]{3,}\.(?:ai|app|cc|com|io|love|online|art|net))\b", text):
                base = match.split(".")[0].replace("-", " ").strip()
                if not base or base.lower() in self.generic_aliases:
                    continue
                display = " ".join(piece.capitalize() for piece in base.split())
                cleaned = self._clean_candidate_name(display, chunk)
                if cleaned:
                    candidates.append(cleaned)
            for match in re.findall(r"\b([A-Z][A-Za-z0-9.-]{2,}\s*/\s*[A-Z][A-Za-z0-9.-]{2,})\b", text):
                cleaned = self._clean_candidate_name(match, chunk)
                if cleaned:
                    candidates.append(cleaned)

        company_pattern = re.compile(
            r"\b("
            r"[A-Z][A-Za-z0-9.&-]+"
            r"(?:\s+[A-Z][A-Za-z0-9.&-]+){0,5}"
            r"\s(?:AI|Technology|Technologies|Systems|Labs|Group|Security|International|Limited|Ltd\.?|Company|Corporation|Corp\.?)"
            r"(?:\s+Co\.,?\s*Ltd\.?)?"
            r")\b"
        )
        for match in company_pattern.findall(text):
            cleaned = self._clean_candidate_name(match.strip(), chunk)
            if cleaned:
                candidates.append(cleaned)

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

    def _normalize_candidate(self, value: str) -> str:
        value = html.unescape(value or "")
        value = re.sub(r"\s+", " ", value).strip(" \t\r\n'\".,;:()[]{}")
        value = re.sub(r"\s*/\s*", " / ", value)
        if " / " in value:
            pieces = [piece.strip() for piece in value.split(" / ") if piece.strip()]
            if pieces:
                value = pieces[0]
        lowered = value.lower()
        for prefix in self.blocked_prefixes:
            if lowered.startswith(prefix):
                value = value[len(prefix) :].strip()
                lowered = value.lower()
        if lowered.startswith("the ") and self._looks_like_company(value[4:]):
            value = value[4:].strip()
        if ". " in value:
            head, tail = value.split(". ", 1)
            if head and len(head.split()) <= 5:
                repeated = tail.lower().startswith(head.lower())
                descriptive_tail = tail.split(" ", 1)[0].lower() in {"the", "a", "an", "israeli", "founded", "based"}
                if repeated or descriptive_tail:
                    value = head.strip()
        return value

    def _clean_candidate_name(self, value: str, chunk: DocumentChunk) -> str:
        candidate = self._normalize_candidate(value)
        if not candidate:
            return ""
        lowered = candidate.lower()
        if lowered in self.generic_aliases or lowered in self.blocked_names:
            return ""
        if lowered in self._source_terms(chunk):
            return ""
        if len(candidate.split()) > 6 and not self._looks_like_company(candidate):
            return ""
        legal_markers = sum(
            marker in lowered
            for marker in [" technology", " technologies", " systems", " limited", " ltd", " corporation", " company", " corp", " group"]
        )
        if legal_markers >= 3 and not self._looks_like_company(candidate):
            return ""
        if any(term in lowered for term in self.headline_terms) and not self._looks_like_company(candidate):
            return ""
        if not self._looks_like_entity(candidate, chunk):
            return ""
        return candidate

    def _looks_like_company(self, value: str) -> bool:
        return bool(
            re.search(
                r"\b(AI|GPT|Technology|Technologies|Systems|Labs|Group|Security|International|Limited|Ltd\.?|Company|Corporation|Corp\.?|Vision|Spy|Watch|Walk)\b",
                value,
                re.IGNORECASE,
            )
        )

    def _source_terms(self, chunk: DocumentChunk) -> set[str]:
        terms = set(self.blocked_names)
        title = html.unescape(chunk.source_title or "").lower()
        for token in re.findall(r"[a-z0-9]+", title):
            if len(token) >= 4:
                terms.add(token)
        parsed = urlparse(chunk.source_url)
        domain = parsed.netloc.lower().replace("www.", "")
        for token in re.findall(r"[a-z0-9]+", domain):
            if len(token) >= 4:
                terms.add(token)
        return terms

    def _local_evidence(self, entity_name: str, text: str) -> str:
        if not entity_name:
            return text
        match = re.search(re.escape(entity_name), text, re.IGNORECASE)
        if not match:
            return text[:500]
        start = max(0, match.start() - 120)
        end = min(len(text), match.end() + 420)
        snippet = text[start:end].strip()
        if start > 0:
            sentence_start = snippet.find(". ")
            if 0 <= sentence_start <= 80:
                snippet = snippet[sentence_start + 2 :].strip()
        return snippet

    def _supports_code(self, evidence_text: str, final_code: str) -> bool:
        if not evidence_text or final_code == "Not included":
            return True
        lowered = evidence_text.lower()
        support_terms = self.code_support_terms.get(final_code, [])
        if any(term in lowered for term in support_terms):
            return True
        if final_code in {"1B", "3A", "3B", "4A"}:
            return False
        return len(evidence_text) >= 140
