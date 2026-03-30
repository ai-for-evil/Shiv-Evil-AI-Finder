from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.pipeline import Pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Evil AI research scraper CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("seed-load")

    crawl_parser = subparsers.add_parser("crawl")
    crawl_parser.add_argument("--sources", type=Path, default=None)

    subparsers.add_parser("clean")
    subparsers.add_parser("classify")
    subparsers.add_parser("dedupe")
    subparsers.add_parser("export")

    run_all_parser = subparsers.add_parser("run-all")
    run_all_parser.add_argument("--sources", type=Path, default=None)

    args = parser.parse_args()
    pipeline = Pipeline()

    if args.command == "seed-load":
        result = pipeline.seed_load()
    elif args.command == "crawl":
        result = pipeline.crawl(args.sources)
    elif args.command == "clean":
        result = pipeline.clean()
    elif args.command == "classify":
        result = pipeline.classify()
    elif args.command == "dedupe":
        result = pipeline.dedupe()
    elif args.command == "export":
        result = pipeline.export()
    elif args.command == "run-all":
        result = pipeline.run_all(args.sources)
    else:
        raise ValueError(f"Unknown command: {args.command}")

    print(json.dumps(result, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
