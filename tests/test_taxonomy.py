import unittest
from pathlib import Path

from src.taxonomy import load_taxonomy


class TaxonomyParsingTests(unittest.TestCase):
    def test_pdf_taxonomy_contains_expected_codes(self):
        root = Path(__file__).resolve().parent.parent
        nodes = load_taxonomy(root / "data" / "seeds" / "ai_for_evil_guidelines.pdf")
        codes = {node.code for node in nodes}
        self.assertIn("1A", codes)
        self.assertIn("4A", codes)
        self.assertIn("5C", codes)
        self.assertEqual(len(nodes), 15)

    def test_gray_area_flags_are_preserved(self):
        root = Path(__file__).resolve().parent.parent
        nodes = load_taxonomy(root / "data" / "seeds" / "ai_for_evil_guidelines.pdf")
        gray_codes = {node.code for node in nodes if node.gray_area}
        self.assertIn("2B", gray_codes)
        self.assertIn("5B", gray_codes)


if __name__ == "__main__":
    unittest.main()
