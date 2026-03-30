import unittest

from src.extractor import EvidenceExtractor
from src.schemas import ClassificationResult, DocumentChunk


class ExtractorTests(unittest.TestCase):
    def setUp(self):
        self.extractor = EvidenceExtractor([])

    def test_filters_publishers_and_generic_names_from_deepfake_article(self):
        chunk = DocumentChunk(
            chunk_id="chunk-1",
            document_id="doc-1",
            source_url="https://www.xbiz.com/news/example",
            source_title="San Francisco City Attorney Sues Nonconsensual Deepfake Porn Sites - XBIZ.com",
            source_type="news",
            publication_date="2024-08-15",
            text=(
                "San Francisco City Attorney sues deepfake nudify sites for creating nonconsensual nude images. "
                "The complaint names ClothOff / Clothoff, Undressai.com, Pornx.ai, and Ainude.ai as sites that "
                "let users undress women and girls with AI-generated fake nude images. Generative AI has promise, "
                "but these services are used for sexual abuse."
            ),
            start_offset=0,
            end_offset=300,
            metadata={},
        )
        classification = ClassificationResult(
            final_code="1B",
            subgroup_name="Synthetic Media Deception",
            confidence=0.91,
            rationale="Strong deepfake indicators.",
        )

        cases = self.extractor.extract_many(
            chunk,
            {"score": 0.95, "reasons": ["matched phrase: deepfake"]},
            classification,
        )
        names = {case.entity_name for case in cases if case.entity_name}

        self.assertIn("ClothOff", names)
        self.assertIn("Undressai", names)
        self.assertIn("Pornx", names)
        self.assertNotIn("Xbiz", names)
        self.assertNotIn("Generative AI", names)
        self.assertNotIn("The AI", names)

    def test_navigation_only_chunk_does_not_emit_named_entities(self):
        chunk = DocumentChunk(
            chunk_id="chunk-2",
            document_id="doc-2",
            source_url="https://misp-galaxy.org/surveillance-vendor/",
            source_title="Surveillance Vendor - MISP galaxy",
            source_type="research_database",
            publication_date="",
            text="CloudWalk Technology ZeroEyes Zencity NSO Group Gamma Group FlexiSPY Table of contents",
            start_offset=0,
            end_offset=100,
            metadata={},
        )
        classification = ClassificationResult(
            final_code="3A",
            subgroup_name="Mass Surveillance Systems",
            confidence=0.88,
            rationale="Vendor list appears surveillance-related.",
        )

        cases = self.extractor.extract_many(
            chunk,
            {"score": 0.8, "reasons": ["prototype similarity max=0.80"]},
            classification,
        )

        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0].entity_name, "")
        self.assertEqual(cases[0].review_status, "missing_entity")


if __name__ == "__main__":
    unittest.main()
