from __future__ import annotations

from pathlib import Path
from typing import List

from src.io_utils import ensure_dir, slugify
from src.schemas import EntityRecord


def write_entity_summaries(records: List[EntityRecord], output_dir: Path) -> None:
    ensure_dir(output_dir)
    for record in records:
        path = output_dir / f"{slugify(record.entity_name)}.md"
        body = [
            f"# {record.entity_name}",
            "",
            f"- Code: {record.canonical_code}",
            f"- Subgroup: {record.subgroup_name}",
            f"- Confidence: {record.confidence:.2f}",
            f"- Review status: {record.review_status}",
            "",
            "## Rationale",
            "",
            record.rationale,
            "",
            "## Evidence",
            "",
        ]
        for evidence in record.evidence_texts[:5]:
            body.append(f"- {evidence}")
        body.extend(["", "## Sources", ""])
        for url in record.source_urls:
            body.append(f"- {url}")
        path.write_text("\n".join(body), encoding="utf-8")
