import unittest

from src.schemas import CandidateCase, TaxonomyNode


class SchemaTests(unittest.TestCase):
    def test_schema_to_dict(self):
        node = TaxonomyNode(
            code="4A",
            subgroup_name="Automated Cyberattack Tools",
            major_group="Cyber and Infrastructure Harm",
            definition="AI systems that identify and exploit digital vulnerabilities.",
            criteria=["Scalable attack capacity"],
        )
        payload = node.to_dict()
        self.assertEqual(payload["code"], "4A")

    def test_candidate_serialization(self):
        case = CandidateCase(
            case_id="case-1",
            entity_name="FraudGPT",
            aliases=["FraudGPT"],
            source_url="https://example.org",
            source_title="Example",
            publication_date="2026-01-01",
            source_type="news",
            evidence_text="Example evidence",
            suspected_function="Automated Cyberattack Tools",
            final_code="4A",
            subgroup_name="Automated Cyberattack Tools",
            confidence=0.9,
            rationale="Evidence grounded",
            review_status="ready_for_review",
            relevance_score=0.8,
        )
        payload = case.to_dict()
        self.assertEqual(payload["entity_name"], "FraudGPT")
        self.assertEqual(payload["final_code"], "4A")


if __name__ == "__main__":
    unittest.main()
