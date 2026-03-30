from __future__ import annotations

import csv
import json
import re
from dataclasses import is_dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def slugify(value: str) -> str:
    value = normalize_whitespace(value).lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "item"


def stable_hash(*parts: str, length: int = 16) -> str:
    joined = "||".join(part or "" for part in parts)
    return sha256(joined.encode("utf-8")).hexdigest()[:length]


def split_multivalue(value: str) -> List[str]:
    if not value:
        return []
    bits = re.split(r"[\n;,]+", value)
    return [normalize_whitespace(bit) for bit in bits if normalize_whitespace(bit)]


def split_aliases(name: str) -> List[str]:
    if not name:
        return []
    aliases = []
    for piece in re.split(r"/|\(|\)|,|\|", name):
        piece = normalize_whitespace(piece)
        if piece and piece.lower() != name.lower():
            aliases.append(piece)
    unique = []
    seen = set()
    for alias in [normalize_whitespace(name)] + aliases:
        key = alias.lower()
        if alias and key not in seen:
            seen.add(key)
            unique.append(alias)
    return unique


def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(_serialize(data), handle, indent=2, ensure_ascii=True)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_jsonl(path: Path, items: Iterable[Any]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            handle.write(json.dumps(_serialize(item), ensure_ascii=True) + "\n")


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    if not rows:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([])
        return
    fieldnames = list(_collect_fieldnames(rows))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _flatten_csv_value(row.get(key)) for key in fieldnames})


def _collect_fieldnames(rows: Sequence[Dict[str, Any]]) -> List[str]:
    names: List[str] = []
    seen = set()
    for row in rows:
        for key in row.keys():
            if key not in seen:
                seen.add(key)
                names.append(key)
    return names


def _flatten_csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " | ".join(_flatten_csv_value(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return str(value)


def _serialize(value: Any) -> Any:
    if is_dataclass(value):
        return _serialize(value.__dict__)
    if hasattr(value, "to_dict"):
        return _serialize(value.to_dict())
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value
