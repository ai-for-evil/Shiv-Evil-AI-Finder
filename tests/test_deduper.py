import unittest

from src.deduper import EntityDeduper
from src.schemas import CandidateCase


class DeduperTests(unittest.TestCase):
    def test_high_similarity_cases_merge(self):
        case_a = CandidateCase(
            case_id="a",
            entity_name="FraudGPT",
            aliases=["FraudGPT"],
            source_url="https://example.org/a",
            source_title="A",
            publication_date="2026-01-01",
            source_type="news",
            evidence_text="FraudGPT used for phishing.",
            suspected_function="Automated Cyberattack Tools",
            final_code="4A",
            subgroup_name="Automated Cyberattack Tools",
            confidence=0.8,
            rationale="test",
            review_status="ready_for_review",
            relevance_score=0.8,
        )
        case_b = CandidateCase(
            case_id="b",
            entity_name="Fraud GPT",
            aliases=["FraudGPT"],
            source_url="https://example.org/b",
            source_title="B",
            publication_date="2026-01-02",
            source_type="threat_report",
            evidence_text="Fraud GPT automates phishing.",
            suspected_function="Automated Cyberattack Tools",
            final_code="4A",
            subgroup_name="Automated Cyberattack Tools",
            confidence=0.82,
            rationale="test",
            review_status="ready_for_review",
            relevance_score=0.85,
        )
        entities, reviews = EntityDeduper().dedupe([case_a, case_b])
        self.assertEqual(len(entities), 1)
        self.assertEqual(len(reviews), 0)


if __name__ == "__main__":
    unittest.main()
