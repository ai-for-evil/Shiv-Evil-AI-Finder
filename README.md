# Evil AI Research Scraper

This repository builds a conservative, evidence-grounded pipeline for documenting publicly reported harmful or abusive AI systems from credible public sources.

The project is designed for research, classification, and human review. It does not discover operational links, invite links, download links, or access paths to harmful systems. Outputs retain public reporting URLs and evidence snippets only.

## What The Project Does

The pipeline:

1. ingests approved public sources,
2. fetches and caches pages,
3. extracts readable article text,
4. scores chunks for relevance,
5. classifies candidates into the project taxonomy,
6. extracts structured evidence,
7. deduplicates repeated entities across sources,
8. exports review-ready CSV, JSONL, and Markdown summaries.

## Source Of Truth Inputs

The project is grounded in two uploaded artifacts that are copied into `data/seeds/`:

- `data/seeds/ai_for_evil_guidelines.pdf`
- `data/seeds/classification_guideline.csv`

### How The PDF Is Parsed

`src/taxonomy.py` extracts the taxonomy definitions from the guideline PDF.

Parsing order:

1. `pypdf` if available
2. `PyPDF2` if available
3. macOS `swift` + `PDFKit` fallback

The parser extracts:

- major groups
- subgroup names
- descriptive definitions
- bullet criteria
- gray-area notes

This yields the internal taxonomy config used by relevance scoring and classification.

### How The CSV Is Parsed

The seed CSV is not a normal row-oriented table. Each example is stored as a column. The parser in `src/taxonomy.py` transposes the sheet into normalized `SeedExample` records.

Recovered fields include:

- final taxonomy code
- tool or entity name
- broad category
- website
- developer or company
- stated use case
- target victim
- primary output
- harm category
- inclusion gates 1 to 3
- exclusion triggers 1 to 3
- include-in-repo label
- one-sentence evidence summary
- evidence links
- reviewer notes

The seed records are used for:

- lexicon building
- code-level prototype similarity
- optional supervised scoring
- regression tests

## Taxonomy

- `1A` Information and Perception Manipulation - Automated Disinformation Systems
- `1B` Information and Perception Manipulation - Synthetic Media Deception
- `1C` Information and Perception Manipulation - Narrative Amplification Engines
- `2A` Exploitation and Manipulation - Predatory Targeting Systems
- `2B` Exploitation and Manipulation - Addiction Optimization Systems
- `2C` Exploitation and Manipulation - Financial Extraction Algorithms
- `3A` Surveillance and Control - Mass Surveillance Systems
- `3B` Surveillance and Control - Predictive Suppression Systems
- `3C` Surveillance and Control - Social Scoring Mechanisms
- `4A` Cyber and Infrastructure Harm - Automated Cyberattack Tools
- `4B` Cyber and Infrastructure Harm - Infrastructure Disruption Systems
- `4C` Cyber and Infrastructure Harm - Autonomous Weaponization
- `5A` Institutional and Structural Manipulation - Metric Gaming Systems
- `5B` Institutional and Structural Manipulation - Market Manipulation Systems
- `5C` Institutional and Structural Manipulation - Accountability Evasion Systems
- `Not included`

Gray-area notes from the uploaded PDF are preserved. In particular, `2B` and `5B` are flagged as likely gray areas, and `3C` plus `5A` have currently undecided criteria.

## Project Layout

```text
.
├── README.md
├── requirements.txt
├── .env.example
├── data
│   ├── processed
│   ├── raw
│   └── seeds
├── outputs
├── scripts
├── src
└── tests
```

## Installation

The code includes standard-library fallbacks for many features, but the recommended install is:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Approved Source Config

Example source manifests live in:

- `data/seeds/approved_sources.example.json`
- `data/seeds/demo_sources.json`

The manifest is intentionally explicit. Each entry declares what kind of source it is and which domains are allowed.

Example:

```json
{
  "sources": [
    {
      "name": "Threat report feed",
      "kind": "rss",
      "url": "https://example.org/feed.xml",
      "source_type": "threat_report",
      "allowed_domains": ["example.org"]
    }
  ]
}
```

Supported `kind` values:

- `url`
- `rss`
- `sitemap`
- `article_list`

The crawler also supports `file://` URLs for offline demos and tests.

## CLI Usage

Run commands with:

```bash
python3 -m src.cli <command> [options]
```

### Seed Load

```bash
python3 -m src.cli seed-load
```

Parses the PDF taxonomy and seed CSV, then writes normalized artifacts to `data/processed/`.

### Crawl

```bash
python3 -m src.cli crawl --sources data/seeds/approved_sources.example.json
```

### Clean

```bash
python3 -m src.cli clean
```

### Classify

```bash
python3 -m src.cli classify
```

### Dedupe

```bash
python3 -m src.cli dedupe
```

### Export

```bash
python3 -m src.cli export
```

### Run All

```bash
python3 -m src.cli run-all --sources data/seeds/demo_sources.json
```

### Continuous Polling

```bash
python3 -m src.cli watch --sources data/seeds/approved_sources.example.json --interval-seconds 3600
```

`watch` keeps polling approved sources, skips already seen URLs, rebuilds the review outputs, and writes newly discovered entities to `outputs/new_entity_records.csv`.

## Demo Run

An offline demo is included:

```bash
bash scripts/demo_run.sh
```

It uses local HTML fixtures in `data/seeds/demo_articles/` so the full pipeline can be exercised without network access.

## Outputs

The pipeline writes these review-ready files to `outputs/`:

- `entity_records.csv`
- `entity_records.jsonl`
- `new_entity_records.csv`
- `new_entity_records.jsonl`
- `review_queue.csv`
- `review_queue.jsonl`
- `crawl_log.csv`
- `entity_summaries/*.md`

Intermediate artifacts are stored in `data/processed/`.

## Classification Strategy

The classification stack is conservative and auditable:

1. rule-based lexicon matching from PDF definitions and seed examples
2. prototype similarity against subgroup descriptions and labeled examples
3. optional supervised scoring if `scikit-learn` is installed
4. confidence penalties for gray areas, weak evidence, or ambiguous margins
5. aggressive fallback to `Not included` when support is weak

The final label is never based on an LLM alone.

## LLM Policy

LLM use is optional and disabled by default.

If enabled, it may only be used for:

- constrained extraction from existing evidence
- summary polishing from already extracted facts

It must not:

- invent missing facts
- choose final labels without rule and model support
- produce operational instructions or access paths

## Tests

The test suite uses `unittest` so it can run in minimal environments:

```bash
python3 -m unittest discover -s tests -v
```

Current tests cover:

- taxonomy parsing from the uploaded PDF
- seed CSV parsing
- classification behavior on seed-like evidence
- deduplication behavior
- schema serialization validation

## Future Improvements

Areas to improve once more labeled data is available:

- replace prototype scoring with calibrated supervised models
- add stronger entity extraction and alias resolution
- improve publication-date extraction
- train separate page-level and chunk-level relevance models
- add active-learning loops from reviewer decisions
- build source-specific article-list extraction rules
