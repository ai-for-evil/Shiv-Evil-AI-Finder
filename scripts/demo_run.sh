#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 -m src.cli run-all --sources data/seeds/demo_sources.json

echo
echo "Demo outputs written to:"
echo "  $ROOT/outputs/entity_records.csv"
echo "  $ROOT/outputs/review_queue.csv"
