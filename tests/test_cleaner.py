import unittest

from src.cleaner import clean_document
from src.schemas import FetchedDocument


class CleanerTests(unittest.TestCase):
    def test_misp_vendor_page_extracts_headings_and_descriptions(self):
        document = FetchedDocument(
            document_id="doc-1",
            url="https://misp-galaxy.org/surveillance-vendor/",
            source_name="MISP Surveillance Vendors",
            source_type="research_database",
            domain="misp-galaxy.org",
            status="ok",
            fetched_at="2026-03-30T00:00:00+00:00",
            title="Surveillance Vendor - MISP galaxy",
        )
        body = """
        <html><body>
        <h2 id="kape-technologies">Kape Technologies</h2>
        <p>Kape Technologies was formerly Crossrider and was associated with malware and adware activity.</p>
        <details><summary>External references</summary><p>https://example.com/reference</p></details>
        <h2 id="nso-group">NSO group</h2>
        <p>NSO Group Technologies is known for Pegasus spyware enabling remote surveillance of smartphones.</p>
        </body></html>
        """

        cleaned = clean_document(document, body)

        self.assertEqual(len(cleaned.paragraphs), 2)
        self.assertIn("Kape Technologies.", cleaned.paragraphs[0])
        self.assertNotIn("example.com/reference", cleaned.cleaned_text)
        self.assertIn("NSO group.", cleaned.paragraphs[1])


if __name__ == "__main__":
    unittest.main()
