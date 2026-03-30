import unittest
from pathlib import Path

from src.classifier import HybridClassifier
from src.taxonomy import load_seed_examples, load_taxonomy


class ClassifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parent.parent
        cls.taxonomy = load_taxonomy(root / "data" / "seeds" / "ai_for_evil_guidelines.pdf")
        cls.seeds = load_seed_examples(root / "data" / "seeds" / "classification_guideline.csv", cls.taxonomy)
        cls.classifier = HybridClassifier(cls.taxonomy, cls.seeds)

    def test_cyberattack_text_maps_to_4a(self):
        text = (
            "Researchers documented a criminal AI tool marketed for phishing emails, exploit code, "
            "and malware assistance without safety controls."
        )
        result = self.classifier.classify(text)
        self.assertEqual(result.final_code, "4A")

    def test_synthetic_media_text_maps_to_1b(self):
        text = (
            "The platform creates realistic fake intimate images from real photos without consent "
            "and is used for deceptive impersonation."
        )
        result = self.classifier.classify(text)
        self.assertEqual(result.final_code, "1B")


if __name__ == "__main__":
    unittest.main()
