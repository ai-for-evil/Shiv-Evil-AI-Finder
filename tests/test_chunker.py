import unittest
from pathlib import Path

from src.chunker import chunk_document
from src.config import load_settings
from src.schemas import CleanDocument


class ChunkerTests(unittest.TestCase):
    def test_splits_long_paragraphs_into_multiple_chunks(self):
        settings = load_settings(Path.cwd())
        settings.max_chunk_chars = 120
        paragraph = (
            "Cloudwalk Technology develops surveillance systems for facial recognition. "
            "Netposa Technologies provides video analytics and police monitoring tools. "
            "Yitu Limited supplies biometric identification and camera-based tracking."
        )
        document = CleanDocument(
            document_id="doc-1",
            source_url="https://example.org/report",
            source_title="Example report",
            source_type="report",
            publication_date="2024-01-01",
            cleaned_text=paragraph,
            paragraphs=[paragraph],
            metadata={},
        )

        chunks = chunk_document(document, settings)

        self.assertGreaterEqual(len(chunks), 2)
        self.assertTrue(all(len(chunk.text) <= 120 for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
