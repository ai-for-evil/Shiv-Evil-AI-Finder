import unittest
from pathlib import Path

from src.taxonomy import load_seed_examples, load_taxonomy


class SeedParserTests(unittest.TestCase):
    def test_seed_parser_transposes_examples(self):
        root = Path(__file__).resolve().parent.parent
        taxonomy = load_taxonomy(root / "data" / "seeds" / "ai_for_evil_guidelines.pdf")
        seeds = load_seed_examples(root / "data" / "seeds" / "classification_guideline.csv", taxonomy)
        self.assertGreaterEqual(len(seeds), 80)

    def test_known_examples_match_expected_labels(self):
        root = Path(__file__).resolve().parent.parent
        taxonomy = load_taxonomy(root / "data" / "seeds" / "ai_for_evil_guidelines.pdf")
        seeds = load_seed_examples(root / "data" / "seeds" / "classification_guideline.csv", taxonomy)
        by_name = {seed.entity_name: seed for seed in seeds}
        self.assertEqual(by_name["FraudGPT"].final_code, "4A")
        self.assertFalse(by_name["Clearview AI Facial Recognition"].include_in_repo)


if __name__ == "__main__":
    unittest.main()
