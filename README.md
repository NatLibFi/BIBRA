# BIBRA
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

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
### Pre-commit hook
Automating the Ruff linter and formatter checks on git commits can be enabled by installing the pre-commit hook:
```bash
uv run pre-commit install
```
Skipping the Ruff checks when committing can be done by adding the `--no-verify` option to the `git commit` command.

## Usage

```bash
uv run uvicorn bibra.main:app
```

## Testing

Run the test suite with:

```bash
uv run pytest
```
## Use of AI Tools

This project uses AI‑powered development tools, including the [RooCode VSCode extension](https://roocode.com/), to support the development process. AI assistance may be used for tasks such as:

- generating and refactoring code
- drafting documentation
- exploring ideas and potential solutions

All AI‑generated content is manually reviewed and approved before being included in the project and the use of AI is disclosed. AI tools do not make decisions independently, as we do not consider their output to be error‑free.
