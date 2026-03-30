from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Sequence


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_-]{1,}")


def tokenize(text: str) -> List[str]:
    return TOKEN_RE.findall((text or "").lower())


def token_counts(text: str) -> Counter:
    return Counter(tokenize(text))


def cosine_similarity(left: Counter, right: Counter) -> float:
    if not left or not right:
        return 0.0
    intersection = set(left) & set(right)
    numerator = sum(left[token] * right[token] for token in intersection)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


class PrototypeClassifier:
    def __init__(self) -> None:
        self.prototypes: Dict[str, Counter] = {}

    def fit(self, labeled_texts: Dict[str, Sequence[str]]) -> "PrototypeClassifier":
        prototypes: Dict[str, Counter] = {}
        for label, texts in labeled_texts.items():
            combined = Counter()
            for text in texts:
                combined.update(token_counts(text))
            prototypes[label] = combined
        self.prototypes = prototypes
        return self

    def score(self, text: str) -> Dict[str, float]:
        query = token_counts(text)
        return {
            label: cosine_similarity(query, prototype)
            for label, prototype in self.prototypes.items()
        }


class KeywordScorer:
    def __init__(self, lexicons: Dict[str, Sequence[str]]) -> None:
        self.lexicons = {code: [entry.lower() for entry in values if entry] for code, values in lexicons.items()}
        self.lexicon_tokens = {
            code: {token for phrase in phrases for token in tokenize(phrase) if len(token) >= 4}
            for code, phrases in self.lexicons.items()
        }

    def score(self, text: str) -> Dict[str, float]:
        lowered = (text or "").lower()
        query_tokens = {token for token in tokenize(lowered) if len(token) >= 4}
        scores: Dict[str, float] = {}
        for code, lexicon in self.lexicons.items():
            hits = 0
            for phrase in lexicon:
                if len(phrase) >= 4 and phrase in lowered:
                    hits += 1
            token_hits = len(query_tokens & self.lexicon_tokens.get(code, set()))
            denominator = max(3, min(12, len(self.lexicon_tokens.get(code, set())) or 3))
            phrase_score = min(1.0, hits / max(1, min(6, max(1, len(lexicon) // 6))))
            token_score = min(1.0, token_hits / denominator)
            scores[code] = max(phrase_score, token_score)
        return scores

    def reasons(self, text: str, top_n: int = 6) -> Dict[str, List[str]]:
        lowered = (text or "").lower()
        query_tokens = {token for token in tokenize(lowered) if len(token) >= 4}
        reasons: Dict[str, List[str]] = defaultdict(list)
        for code, lexicon in self.lexicons.items():
            for phrase in lexicon:
                if len(phrase) >= 4 and phrase in lowered and len(reasons[code]) < top_n:
                    reasons[code].append(phrase)
            if len(reasons[code]) < top_n:
                for token in sorted(query_tokens & self.lexicon_tokens.get(code, set())):
                    if token not in reasons[code]:
                        reasons[code].append(token)
                    if len(reasons[code]) >= top_n:
                        break
        return dict(reasons)


class OptionalSklearnTextClassifier:
    def __init__(self) -> None:
        self.available = False
        self.labels: List[str] = []
        self.pipeline = None
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.linear_model import LogisticRegression
            from sklearn.pipeline import Pipeline

            self._pipeline_cls = Pipeline
            self._vectorizer_cls = TfidfVectorizer
            self._classifier_cls = LogisticRegression
            self.available = True
        except Exception:
            self.available = False

    def fit(self, texts: Sequence[str], labels: Sequence[str]) -> "OptionalSklearnTextClassifier":
        if not self.available or not texts:
            return self
        self.labels = sorted(set(labels))
        self.pipeline = self._pipeline_cls(
            [
                ("tfidf", self._vectorizer_cls(ngram_range=(1, 2), min_df=1)),
                ("clf", self._classifier_cls(max_iter=2000)),
            ]
        )
        self.pipeline.fit(list(texts), list(labels))
        return self

    def score(self, text: str) -> Dict[str, float]:
        if not self.available or self.pipeline is None:
            return {}
        probabilities = self.pipeline.predict_proba([text])[0]
        return {
            label: float(probability)
            for label, probability in zip(self.pipeline.classes_, probabilities)
        }
