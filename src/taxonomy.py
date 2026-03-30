from __future__ import annotations

import csv
import platform
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from src.io_utils import normalize_whitespace, split_aliases, split_multivalue
from src.schemas import SeedExample, TaxonomyNode


MAJOR_GROUP_RE = re.compile(r"^(?:[0-9IVX]+)\s*\.?\s+(.+)$")
SUBGROUP_RE = re.compile(r"^([A-C])\.\s+(.+)$")
PAGE_RE = re.compile(r"^\d+$")


def extract_pdf_text(pdf_path: Path) -> str:
    for module_name in ("pypdf", "PyPDF2"):
        try:
            module = __import__(module_name)
            reader_cls = getattr(module, "PdfReader")
            reader = reader_cls(str(pdf_path))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:
            continue

    if platform.system() == "Darwin":
        return _extract_pdf_text_with_swift(pdf_path)

    raise RuntimeError("Unable to extract PDF text. Install pypdf or run on macOS with swift/PDFKit.")


def _extract_pdf_text_with_swift(pdf_path: Path) -> str:
    script = (
        "import Foundation; import PDFKit; "
        f'let url = URL(fileURLWithPath: "{pdf_path}"); '
        "guard let doc = PDFDocument(url: url) else { fatalError(\"failed\") }; "
        "for i in 0..<doc.pageCount { print(doc.page(at: i)?.string ?? \"\") }"
    )
    cmd = [
        "env",
        "CLANG_MODULE_CACHE_PATH=/tmp/clang-module-cache",
        "SWIFT_MODULECACHE_PATH=/tmp/swift-module-cache",
        "swift",
        "-e",
        script,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout


def load_taxonomy(pdf_path: Path) -> List[TaxonomyNode]:
    text = extract_pdf_text(pdf_path)
    return parse_taxonomy_text(text)


def parse_taxonomy_text(text: str) -> List[TaxonomyNode]:
    lines = [normalize_whitespace(line) for line in (text or "").splitlines()]
    lines = [line for line in lines if line and not PAGE_RE.match(line)]

    nodes: List[TaxonomyNode] = []
    current_major = ""
    current_major_index = 0
    current_letter = ""
    current_title = ""
    current_lines: List[str] = []

    def flush() -> None:
        nonlocal current_lines
        if not current_title or not current_letter or not current_major:
            current_lines = []
            return
        definition = ""
        criteria: List[str] = []
        gray_area = "gray area" in current_title.lower() or "criteria currently undecided" in current_title.lower()
        notes: List[str] = []
        if gray_area:
            notes.append(current_title)
        for line in current_lines:
            if "gray area" in line.lower():
                gray_area = True
                notes.append(line)
                continue
            if "criteria currently undecided" in line.lower():
                gray_area = True
                notes.append(line)
                continue
            if not definition:
                definition = line
            else:
                criteria.append(line.replace("●", "").strip())
        code = f"{current_major_index}{current_letter}"
        nodes.append(
            TaxonomyNode(
                code=code,
                subgroup_name=current_title,
                major_group=current_major,
                definition=definition,
                criteria=criteria,
                gray_area=gray_area,
                confidence_notes=" ".join(notes),
            )
        )
        current_lines = []

    for line in lines:
        if line.startswith("Shivansh Sahni"):
            continue
        if line.startswith("Classification Guidelines:"):
            continue
        if line.startswith("(") and "Preliminary Ideas" in line:
            continue

        major_match = MAJOR_GROUP_RE.match(line)
        if major_match:
            flush()
            current_major = major_match.group(1).strip()
            current_major_index += 1
            current_letter = ""
            current_title = ""
            continue

        subgroup_match = SUBGROUP_RE.match(line)
        if subgroup_match:
            flush()
            current_letter = subgroup_match.group(1).strip()
            current_title = subgroup_match.group(2).strip()
            continue

        if current_title:
            current_lines.append(line)

    flush()
    return nodes


def taxonomy_by_code(nodes: List[TaxonomyNode]) -> Dict[str, TaxonomyNode]:
    return {node.code: node for node in nodes}


def load_seed_examples(csv_path: Path, nodes: List[TaxonomyNode]) -> List[SeedExample]:
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))

    taxonomy_map = taxonomy_by_code(nodes)
    label_row = rows[4]
    reviewer_row = rows[5]
    frame_row = rows[6]
    name_row = rows[7]
    broad_category_row = rows[8]
    url_row = rows[9]
    developer_row = rows[10]
    tagline_row = rows[11]
    use_case_row = rows[12]
    target_row = rows[13]
    output_row = rows[14]
    harm_row = rows[15]
    gate1_row = rows[16]
    gate2_row = rows[17]
    gate3_row = rows[18]
    exclusion1_row = rows[19]
    exclusion2_row = rows[20]
    exclusion3_row = rows[21]
    include_row = rows[22]
    summary_row = rows[23]
    links_row = rows[24]
    notes_row = rows[25]

    examples: List[SeedExample] = []
    max_cols = max(len(row) for row in rows)
    for column in range(2, max_cols):
        entity_name = _cell(name_row, column)
        if not entity_name:
            continue
        final_code = _cell(label_row, column)
        taxonomy = taxonomy_map.get(final_code)
        examples.append(
            SeedExample(
                entity_name=entity_name,
                final_code=final_code,
                subgroup_name=taxonomy.subgroup_name if taxonomy else ("Not included" if final_code == "Not included" else ""),
                broad_category=_cell(broad_category_row, column),
                source_url=_cell(url_row, column),
                developer=_cell(developer_row, column),
                tagline=_cell(tagline_row, column),
                stated_use_case=_cell(use_case_row, column),
                target_victim=_cell(target_row, column),
                primary_output=_cell(output_row, column),
                harm_category=_cell(harm_row, column),
                evidence_summary=_cell(summary_row, column),
                evidence_links=split_multivalue(_cell(links_row, column)),
                reviewer_notes=_cell(notes_row, column),
                reviewer_name=_cell(reviewer_row, column),
                criminality_frame=_cell(frame_row, column),
                gates={
                    "gate_1": _cell(gate1_row, column).upper() == "Y",
                    "gate_2": _cell(gate2_row, column).upper() == "Y",
                    "gate_3": _cell(gate3_row, column).upper() == "Y",
                },
                exclusions={
                    "exclusion_1": _cell(exclusion1_row, column).upper() == "Y",
                    "exclusion_2": _cell(exclusion2_row, column).upper() == "Y",
                    "exclusion_3": _cell(exclusion3_row, column).upper() == "Y",
                },
                include_in_repo=_parse_bool(_cell(include_row, column)),
                aliases=split_aliases(entity_name),
            )
        )
    return examples


def build_code_lexicons(nodes: List[TaxonomyNode], seeds: List[SeedExample]) -> Dict[str, List[str]]:
    lexicons: Dict[str, List[str]] = defaultdict(list)
    for node in nodes:
        lexicons[node.code].extend(
            [
                node.subgroup_name,
                node.major_group,
                node.definition,
                *node.criteria,
            ]
        )
    for example in seeds:
        if not example.final_code or example.final_code == "Not included":
            continue
        lexicons[example.final_code].extend(
            [
                example.entity_name,
                *example.aliases,
                example.broad_category,
                example.tagline,
                example.stated_use_case,
                example.primary_output,
                example.harm_category,
                example.evidence_summary,
            ]
        )

    cleaned: Dict[str, List[str]] = {}
    for code, phrases in lexicons.items():
        seen = set()
        cleaned_phrases: List[str] = []
        for phrase in phrases:
            phrase = normalize_whitespace(phrase)
            if not phrase:
                continue
            lower = phrase.lower()
            if lower not in seen:
                seen.add(lower)
                cleaned_phrases.append(phrase)
        cleaned[code] = cleaned_phrases
    return cleaned


def build_reference_texts(nodes: List[TaxonomyNode], seeds: List[SeedExample]) -> Dict[str, List[str]]:
    references: Dict[str, List[str]] = defaultdict(list)
    for node in nodes:
        references[node.code].append(
            " ".join(
                [
                    node.subgroup_name,
                    node.major_group,
                    node.definition,
                    " ".join(node.criteria),
                    node.confidence_notes,
                ]
            )
        )
    for example in seeds:
        if not example.final_code or example.final_code == "Not included":
            continue
        references[example.final_code].append(
            " ".join(
                [
                    example.entity_name,
                    example.broad_category,
                    example.tagline,
                    example.stated_use_case,
                    example.primary_output,
                    example.harm_category,
                    example.evidence_summary,
                ]
            )
        )
    return references


def _cell(row: List[str], column: int) -> str:
    return normalize_whitespace(row[column]) if column < len(row) else ""


def _parse_bool(value: str) -> bool | None:
    upper = value.strip().upper()
    if upper == "Y":
        return True
    if upper == "N":
        return False
    return None
