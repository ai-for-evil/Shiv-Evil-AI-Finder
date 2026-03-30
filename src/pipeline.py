from __future__ import annotations

import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from src.chunker import chunk_document
from src.classifier import HybridClassifier
from src.cleaner import clean_document
from src.config import Settings, load_settings
from src.crawler import Crawler
from src.deduper import EntityDeduper
from src.extractor import EvidenceExtractor
from src.io_utils import read_jsonl, stable_hash, write_csv, write_json, write_jsonl
from src.relevance import RelevanceScorer
from src.review_queue import build_review_queue
from src.schemas import CandidateCase, CrawlLogEntry, EntityRecord, FetchedDocument, ReviewItem
from src.sources import allowed_target, discovery_urls, load_sources, parse_feed_items, resolve_targets
from src.summarizer import write_entity_summaries
from src.taxonomy import load_seed_examples, load_taxonomy


class Pipeline:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()

    def seed_load(self) -> dict:
        taxonomy = load_taxonomy(self.settings.guidelines_pdf_path)
        seeds = load_seed_examples(self.settings.seed_csv_path, taxonomy)
        write_json(self.settings.processed_dir / "taxonomy.json", [node.to_dict() for node in taxonomy])
        write_jsonl(self.settings.processed_dir / "seed_examples.jsonl", [seed.to_dict() for seed in seeds])
        write_csv(self.settings.processed_dir / "seed_examples.csv", [seed.to_dict() for seed in seeds])
        return {"taxonomy_count": len(taxonomy), "seed_count": len(seeds)}

    def crawl(self, source_manifest: Path | None = None, incremental: bool = True) -> dict:
        manifest = source_manifest or self.settings.source_config_path
        sources = load_sources(manifest)
        crawler = Crawler(self.settings)
        existing_documents = read_jsonl(self.settings.processed_dir / "fetched_documents.jsonl") if incremental else []
        existing_by_url = {item["url"]: item for item in existing_documents if item.get("url")}
        seen_urls = {url for url, item in existing_by_url.items() if item.get("status") == "ok"}

        documents = list(existing_by_url.values())
        logs = []
        new_documents = 0
        skipped_urls = 0

        for source in sources:
            targets = [source.url]
            if source.kind in {"bing_news_search", "google_news_search"}:
                for discovery_url in discovery_urls(source):
                    manifest_doc, manifest_log, manifest_body = crawler.fetch(source, discovery_url)
                    logs.append(manifest_log.to_dict())
                    if manifest_doc.status != "ok":
                        continue
                    for item in parse_feed_items(source, manifest_body):
                        if not allowed_target(item["url"], source.allowed_domains):
                            continue
                        if incremental and item["url"] in seen_urls:
                            skipped_urls += 1
                            continue
                        document, log = _fetch_or_stub_search_item(self.settings, crawler, source, item)
                        existing_by_url[item["url"]] = document.to_dict()
                        logs.append(log.to_dict())
                        new_documents += 1
                continue
            if source.kind != "url":
                targets = []
                for discovery_url in discovery_urls(source):
                    manifest_doc, manifest_log, manifest_body = crawler.fetch(source, discovery_url)
                    logs.append(manifest_log.to_dict())
                    if manifest_doc.status != "ok":
                        continue
                    for url in resolve_targets(source, manifest_body):
                        if allowed_target(url, source.allowed_domains):
                            targets.append(url)
                targets = list(dict.fromkeys(targets))

            for target in targets:
                if incremental and target in seen_urls:
                    skipped_urls += 1
                    continue
                document, log, _body = crawler.fetch(source, target)
                existing_by_url[target] = document.to_dict()
                logs.append(log.to_dict())
                if document.status == "ok":
                    new_documents += 1

        documents = list(existing_by_url.values())
        write_jsonl(self.settings.processed_dir / "fetched_documents.jsonl", documents)
        write_csv(self.settings.outputs_dir / "crawl_log.csv", logs)
        write_jsonl(self.settings.outputs_dir / "crawl_log.jsonl", logs)
        return {
            "document_count": len(documents),
            "new_document_count": new_documents,
            "skipped_known_urls": skipped_urls,
            "log_count": len(logs),
        }

    def clean(self) -> dict:
        raw_documents = read_jsonl(self.settings.processed_dir / "fetched_documents.jsonl")
        cleaned_docs = []
        chunks = []
        for item in raw_documents:
            if item.get("status") != "ok" or not item.get("raw_path"):
                continue
            if item.get("text_path", "").endswith(".txt") and Path(item["text_path"]).exists():
                body = Path(item["text_path"]).read_text(encoding="utf-8")
            else:
                body = Path(item["raw_path"]).read_text(encoding="utf-8")
            document = clean_document(_fetched_from_dict(item), body)
            cleaned_docs.append(document.to_dict())
            for chunk in chunk_document(document, self.settings):
                chunks.append(chunk.to_dict())

        write_jsonl(self.settings.processed_dir / "clean_documents.jsonl", cleaned_docs)
        write_jsonl(self.settings.processed_dir / "chunks.jsonl", chunks)
        return {"clean_document_count": len(cleaned_docs), "chunk_count": len(chunks)}

    def classify(self) -> dict:
        taxonomy = load_taxonomy(self.settings.guidelines_pdf_path)
        seeds = load_seed_examples(self.settings.seed_csv_path, taxonomy)
        chunks = read_jsonl(self.settings.processed_dir / "chunks.jsonl")
        relevance_scorer = RelevanceScorer(taxonomy, seeds)
        classifier = HybridClassifier(taxonomy, seeds, threshold=self.settings.classification_threshold)
        extractor = EvidenceExtractor(seeds)

        cases: List[CandidateCase] = []
        for chunk_dict in chunks:
            chunk = _chunk_from_dict(chunk_dict)
            relevance = relevance_scorer.score(chunk)
            if float(relevance["score"]) < self.settings.relevance_threshold:
                continue
            classification = classifier.classify(chunk.text)
            for case in extractor.extract_many(chunk, relevance, classification):
                cases.append(case)

        write_jsonl(self.settings.processed_dir / "candidate_cases.jsonl", [case.to_dict() for case in cases])
        return {"candidate_count": len(cases)}

    def dedupe(self) -> dict:
        case_dicts = read_jsonl(self.settings.processed_dir / "candidate_cases.jsonl")
        cases = [_candidate_from_dict(item) for item in case_dicts]
        taxonomy = load_taxonomy(self.settings.guidelines_pdf_path)
        seeds = load_seed_examples(self.settings.seed_csv_path, taxonomy)
        deduper = EntityDeduper()
        previous_entities = read_jsonl(self.settings.processed_dir / "entity_records.jsonl")
        previous_ids = {item.get("entity_id") for item in previous_entities}
        seed_names = [seed.entity_name for seed in seeds]
        entities, duplicate_reviews = deduper.dedupe(cases, seed_names=seed_names)
        new_entities = [entity for entity in entities if entity.entity_id not in previous_ids]
        novel_entities = [
            entity
            for entity in entities
            if not entity.seed_overlap and entity.canonical_code and entity.canonical_code != "Not included"
        ]
        reviews = build_review_queue(cases, duplicate_reviews)
        write_jsonl(self.settings.processed_dir / "entity_records.jsonl", [entity.to_dict() for entity in entities])
        write_jsonl(self.settings.processed_dir / "new_entity_records.jsonl", [entity.to_dict() for entity in new_entities])
        write_jsonl(self.settings.processed_dir / "novel_entity_records.jsonl", [entity.to_dict() for entity in novel_entities])
        write_jsonl(self.settings.processed_dir / "review_queue.jsonl", [review.to_dict() for review in reviews])
        return {
            "entity_count": len(entities),
            "new_entity_count": len(new_entities),
            "novel_entity_count": len(novel_entities),
            "review_count": len(reviews),
        }

    def export(self) -> dict:
        entities = read_jsonl(self.settings.processed_dir / "entity_records.jsonl")
        new_entities = read_jsonl(self.settings.processed_dir / "new_entity_records.jsonl")
        novel_entities = read_jsonl(self.settings.processed_dir / "novel_entity_records.jsonl")
        reviews = read_jsonl(self.settings.processed_dir / "review_queue.jsonl")
        write_csv(self.settings.outputs_dir / "entity_records.csv", entities)
        write_jsonl(self.settings.outputs_dir / "entity_records.jsonl", entities)
        write_csv(self.settings.outputs_dir / "new_entity_records.csv", new_entities)
        write_jsonl(self.settings.outputs_dir / "new_entity_records.jsonl", new_entities)
        write_csv(self.settings.outputs_dir / "novel_entity_records.csv", novel_entities)
        write_jsonl(self.settings.outputs_dir / "novel_entity_records.jsonl", novel_entities)
        write_csv(self.settings.outputs_dir / "review_queue.csv", reviews)
        write_jsonl(self.settings.outputs_dir / "review_queue.jsonl", reviews)
        write_entity_summaries([_entity_from_dict(item) for item in entities], self.settings.outputs_dir / "entity_summaries")
        return {
            "entity_count": len(entities),
            "new_entity_count": len(new_entities),
            "novel_entity_count": len(novel_entities),
            "review_count": len(reviews),
        }

    def run_all(self, source_manifest: Path | None = None, incremental: bool = True) -> dict:
        summary = {}
        summary["seed_load"] = self.seed_load()
        summary["crawl"] = self.crawl(source_manifest, incremental=incremental)
        summary["clean"] = self.clean()
        summary["classify"] = self.classify()
        summary["dedupe"] = self.dedupe()
        summary["export"] = self.export()
        return summary

    def watch(self, source_manifest: Path | None = None, interval_seconds: int = 3600, max_cycles: int | None = None, fresh_first_cycle: bool = False) -> dict:
        summary = {"cycles": []}
        cycle = 0
        self.seed_load()
        while True:
            cycle += 1
            cycle_summary = self.run_cycle(source_manifest, incremental=not (fresh_first_cycle and cycle == 1))
            cycle_summary["cycle"] = cycle
            summary["cycles"].append(cycle_summary)
            if max_cycles is not None and cycle >= max_cycles:
                break
            time.sleep(interval_seconds)
        return summary

    def run_cycle(self, source_manifest: Path | None = None, incremental: bool = True) -> dict:
        summary = {}
        summary["crawl"] = self.crawl(source_manifest, incremental=incremental)
        summary["clean"] = self.clean()
        summary["classify"] = self.classify()
        summary["dedupe"] = self.dedupe()
        summary["export"] = self.export()
        return summary


def _fetched_from_dict(item: dict):
    from src.schemas import FetchedDocument

    return FetchedDocument(**item)


def _chunk_from_dict(item: dict):
    from src.schemas import DocumentChunk

    return DocumentChunk(**item)


def _candidate_from_dict(item: dict) -> CandidateCase:
    from src.schemas import CandidateCase

    return CandidateCase(**item)


def _entity_from_dict(item: dict) -> EntityRecord:
    from src.schemas import EntityRecord

    return EntityRecord(**item)


def _search_item_to_document(settings: Settings, source, item: dict) -> tuple[FetchedDocument, CrawlLogEntry]:
    document_id = stable_hash(item["url"])
    raw_path = settings.raw_dir / f"{document_id}.raw"
    title = item.get("title", "")
    description = item.get("description", "")
    publication_date = item.get("publication_date", "")
    body = (
        "<html><head><title>{title}</title></head><body><article><h1>{title}</h1>"
        "<p>{description}</p><p>Reported by {source_name}</p></article></body></html>"
    ).format(title=title, description=description, source_name=item.get("source_name", source.name))
    raw_path.write_text(body, encoding="utf-8")
    fetched_at = datetime.now(timezone.utc).isoformat()
    document = FetchedDocument(
        document_id=document_id,
        url=item["url"],
        source_name=source.name,
        source_type=source.source_type,
        domain=Path(item["url"]).name if item["url"].startswith("file://") else urllib.parse.urlparse(item["url"]).netloc.lower(),
        status="ok",
        fetched_at=fetched_at,
        title=title,
        publication_date=publication_date,
        raw_path=str(raw_path),
        text_path="",
        http_status=200,
        error="",
    )
    log = CrawlLogEntry(
        url=item["url"],
        source_name=source.name,
        status="ok_stub",
        fetched_at=fetched_at,
        http_status=200,
        raw_path=str(raw_path),
        error="",
    )
    return document, log


def _fetch_or_stub_search_item(settings: Settings, crawler: Crawler, source, item: dict) -> tuple[FetchedDocument, CrawlLogEntry]:
    document, log, _body = crawler.fetch(source, item["url"])
    if document.status == "ok":
        if not document.title:
            document.title = item.get("title", "")
        if not document.publication_date:
            document.publication_date = item.get("publication_date", "")
        return document, log
    return _search_item_to_document(settings, source, item)
