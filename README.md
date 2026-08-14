# BIBRA
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/NatLibFi/BIBRA/actions/workflows/tests.yml/badge.svg)](https://github.com/NatLibFi/BIBRA/actions/workflows/tests.yml)
[![CodeQL](https://github.com/NatLibFi/BIBRA/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/NatLibFi/BIBRA/actions/workflows/github-code-scanning/codeql)
[![codecov](https://codecov.io/gh/NatLibFi/BIBRA/branch/main/graph/badge.svg)](https://codecov.io/gh/NatLibFi/BIBRA)
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
Install development dependencies:
```bash
uv sync
```
Alternatively, install as a global CLI tool (in editable mode) so prefixing CLI commands with `uv run` is not needed:
```bash
uv tool install -e .
```
Install web UI dependencies:
```bash
npm install
```

### Pre-commit hook
Automating the Ruff linter and formatter checks on git commits can be enabled by installing the pre-commit hook:
```bash
uv run pre-commit install
```
Skipping the Ruff checks when committing can be done by adding the `--no-verify` option to the `git commit` command.

## Usage
See the available CLI commands:
```bash
uv run bibra
```
Start up the server:
```bash
uv run uvicorn bibra.main:app
```

## Testing

### Python Tests

Run the Python test suite with:

```bash
uv run pytest
```

### Cypress E2E Tests

Run the Cypress end-to-end tests:

**Run Cypress in interactive mode (opens Cypress GUI):**
```bash
npx cypress open
```

**Run Cypress headless**

```bash
npm run cy:run
```

## Use of AI Tools

This project uses AI‑powered development tools, including the [Zoo Code VSCode extension](https://www.zoocode.dev/), to support the development process. AI assistance may be used for tasks such as:

- generating and refactoring code and tests
- drafting documentation
- exploring ideas and potential solutions

All LLM‑generated content is manually reviewed and approved before being included in the project and the use of AI is disclosed via the [pull request template](.github/PULL_REQUEST_TEMPLATE.md). We indicate AI use, how much human effort went into the work and especially into verifying the result of AI using the [AI Traffic Lights Protocol](https://nlkw.de/en/blog/ai-tlp/) by Nila Löber. AI:ORANGE is the minimum level required for merging pull requests.
