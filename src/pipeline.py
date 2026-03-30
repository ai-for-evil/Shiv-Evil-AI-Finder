from __future__ import annotations

from pathlib import Path
from typing import List

from src.chunker import chunk_document
from src.classifier import HybridClassifier
from src.cleaner import clean_document
from src.config import Settings, load_settings
from src.crawler import Crawler
from src.deduper import EntityDeduper
from src.extractor import EvidenceExtractor
from src.io_utils import read_jsonl, write_csv, write_json, write_jsonl
from src.relevance import RelevanceScorer
from src.review_queue import build_review_queue
from src.schemas import CandidateCase, EntityRecord, ReviewItem
from src.sources import allowed_target, load_sources, resolve_targets
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

    def crawl(self, source_manifest: Path | None = None) -> dict:
        manifest = source_manifest or self.settings.source_config_path
        sources = load_sources(manifest)
        crawler = Crawler(self.settings)
        documents = []
        logs = []

        for source in sources:
            targets = [source.url]
            if source.kind != "url":
                manifest_doc, _, manifest_body = crawler.fetch(source, source.url)
                logs.append(manifest_doc.to_dict())
                if manifest_doc.status != "ok":
                    continue
                targets = [url for url in resolve_targets(source, manifest_body) if allowed_target(url, source.allowed_domains)]

            for target in targets:
                document, log, _body = crawler.fetch(source, target)
                documents.append(document.to_dict())
                logs.append(log.to_dict())

        write_jsonl(self.settings.processed_dir / "fetched_documents.jsonl", documents)
        write_csv(self.settings.outputs_dir / "crawl_log.csv", logs)
        write_jsonl(self.settings.outputs_dir / "crawl_log.jsonl", logs)
        return {"document_count": len(documents), "log_count": len(logs)}

    def clean(self) -> dict:
        raw_documents = read_jsonl(self.settings.processed_dir / "fetched_documents.jsonl")
        cleaned_docs = []
        chunks = []
        for item in raw_documents:
            if item.get("status") != "ok" or not item.get("raw_path"):
                continue
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
            case = extractor.extract(chunk, relevance, classification)
            cases.append(case)

        write_jsonl(self.settings.processed_dir / "candidate_cases.jsonl", [case.to_dict() for case in cases])
        return {"candidate_count": len(cases)}

    def dedupe(self) -> dict:
        case_dicts = read_jsonl(self.settings.processed_dir / "candidate_cases.jsonl")
        cases = [_candidate_from_dict(item) for item in case_dicts]
        deduper = EntityDeduper()
        entities, duplicate_reviews = deduper.dedupe(cases)
        reviews = build_review_queue(cases, duplicate_reviews)
        write_jsonl(self.settings.processed_dir / "entity_records.jsonl", [entity.to_dict() for entity in entities])
        write_jsonl(self.settings.processed_dir / "review_queue.jsonl", [review.to_dict() for review in reviews])
        return {"entity_count": len(entities), "review_count": len(reviews)}

    def export(self) -> dict:
        entities = read_jsonl(self.settings.processed_dir / "entity_records.jsonl")
        reviews = read_jsonl(self.settings.processed_dir / "review_queue.jsonl")
        write_csv(self.settings.outputs_dir / "entity_records.csv", entities)
        write_jsonl(self.settings.outputs_dir / "entity_records.jsonl", entities)
        write_csv(self.settings.outputs_dir / "review_queue.csv", reviews)
        write_jsonl(self.settings.outputs_dir / "review_queue.jsonl", reviews)
        write_entity_summaries([_entity_from_dict(item) for item in entities], self.settings.outputs_dir / "entity_summaries")
        return {"entity_count": len(entities), "review_count": len(reviews)}

    def run_all(self, source_manifest: Path | None = None) -> dict:
        summary = {}
        summary["seed_load"] = self.seed_load()
        summary["crawl"] = self.crawl(source_manifest)
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
