# BIBRA

A metadata extraction and verification tool that integrates multiple methods for extracting, verifying, and reconciling metadata.

## Features

- **Metadata Extraction**: Multiple methods including LLM prompting, fine-tuned models, traditional NLP, and machine learning
- **Verification & Benchmarking**: Tools for verifying quality against gold standard/ground truth datasets
- **External Integration**: Authority control and vocabulary reconciliation with external systems
- **Web UI**: Interactive interface for metadata processing
- **REST API**: Backend microservice for integration with cataloging tools and data enrichment processes

## Installation

```bash
uv sync
```

## Usage

```bash
python main.py
```

## Testing

Run the test suite with:

```bash
uv sync --group dev
uv run pytest
```

Or run tests with verbose output:

```bash
uv run pytest -v
```
