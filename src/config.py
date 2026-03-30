from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

from src.io_utils import ensure_dir


@dataclass
class Settings:
    project_root: Path
    data_dir: Path
    raw_dir: Path
    processed_dir: Path
    seeds_dir: Path
    outputs_dir: Path
    seed_csv_path: Path
    guidelines_pdf_path: Path
    source_config_path: Path
    use_llm: bool = False
    rate_limit_seconds: float = 1.0
    max_chunk_chars: int = 1200
    relevance_threshold: float = 0.38
    classification_threshold: float = 0.46
    review_confidence_threshold: float = 0.60
    high_confidence_threshold: float = 0.75


def load_settings(project_root: Path | None = None) -> Settings:
    root = project_root or Path(__file__).resolve().parent.parent
    data_dir = root / "data"
    raw_dir = data_dir / "raw"
    processed_dir = data_dir / "processed"
    seeds_dir = data_dir / "seeds"
    outputs_dir = root / "outputs"

    for directory in [data_dir, raw_dir, processed_dir, seeds_dir, outputs_dir]:
        ensure_dir(directory)

    use_llm = os.getenv("AI_EVIL_USE_LLM", "false").lower() == "true"
    return Settings(
        project_root=root,
        data_dir=data_dir,
        raw_dir=raw_dir,
        processed_dir=processed_dir,
        seeds_dir=seeds_dir,
        outputs_dir=outputs_dir,
        seed_csv_path=root / "data" / "seeds" / "classification_guideline.csv",
        guidelines_pdf_path=root / "data" / "seeds" / "ai_for_evil_guidelines.pdf",
        source_config_path=Path(os.getenv("AI_EVIL_SOURCE_CONFIG", str(root / "data" / "seeds" / "approved_sources.example.json"))),
        use_llm=use_llm,
        rate_limit_seconds=float(os.getenv("AI_EVIL_RATE_LIMIT_SECONDS", "1.0")),
        max_chunk_chars=int(os.getenv("AI_EVIL_MAX_CHUNK_CHARS", "1200")),
        relevance_threshold=float(os.getenv("AI_EVIL_RELEVANCE_THRESHOLD", "0.38")),
        classification_threshold=float(os.getenv("AI_EVIL_CLASSIFICATION_THRESHOLD", "0.46")),
        review_confidence_threshold=float(os.getenv("AI_EVIL_REVIEW_CONFIDENCE_THRESHOLD", "0.60")),
        high_confidence_threshold=float(os.getenv("AI_EVIL_HIGH_CONFIDENCE_THRESHOLD", "0.75")),
    )


def load_manifest(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload.get("sources", [])
