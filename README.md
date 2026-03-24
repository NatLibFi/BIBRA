# BIBRA

> **Note**: The name "BIBRA" is a working title and may still change. The application is still heavily work in progress and not yet functional.

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
uv run uvicorn bibra.main:app
```

## Testing

Run the test suite with:

```bash
uv run pytest
```
