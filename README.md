# BIBRA
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![CI/CD](https://github.com/NatLibFi/BIBRA/actions/workflows/cicd.yml/badge.svg)](https://github.com/NatLibFi/BIBRA/actions/workflows/cicd.yml)
[![CodeQL](https://github.com/NatLibFi/BIBRA/actions/workflows/github-code-scanning/codeql/badge.svg)](https://github.com/NatLibFi/BIBRA/actions/workflows/github-code-scanning/codeql)
[![codecov](https://codecov.io/gh/NatLibFi/BIBRA/branch/main/graph/badge.svg)](https://codecov.io/gh/NatLibFi/BIBRA)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

A metadata extraction and verification tool that integrates multiple methods for extracting, verifying, and reconciling metadata.

## Features

- **Metadata Extraction**: Multiple methods including LLM prompting, fine-tuned models, traditional NLP, and machine learning
- **Verification & Benchmarking**: Tools for verifying quality against gold standard/ground truth datasets
- **External Integration**: Authority control and vocabulary reconciliation with external systems
- **Web UI**: Interactive interface for metadata processing
- **REST API**: Backend microservice for integration with cataloging tools and data enrichment processes

## Install via PyPI

Install the latest release of the [bibra](https://pypi.org/project/bibra/) package from PyPI into a fresh Python virtualenv:

    pip install bibra

## Use via Docker

We publish Docker images on Quay.io with the name [natlibfi/bibra](https://quay.io/repository/natlibfi/bibra).
To run a shell within the image, use the command

    docker run -it --rm quay.io/natlibfi/bibra bash

If you don't specify the command to run, the image will start a Uvicorn server for the REST API and Web UI on [port 8000](http://0.0.0.0:8000):

    docker run -it --rm quay.io/natlibfi/bibra

## Getting started

See the [wiki](https://github.com/NatLibFi/BIBRA/wiki) for documentation on setting up and configuring BIBRA and LLM services.

## Development install

Install development dependencies:

    uv sync

Alternatively, install as a global CLI tool (in editable mode) so prefixing CLI commands with `uv run` is not needed:

    uv tool install -e .

Install web UI dependencies:

    npm install

### Pre-commit hook

Automating the Ruff linter and formatter checks on git commits can be enabled by installing the pre-commit hook:

    uv run pre-commit install

Skipping the Ruff checks when committing can be done by adding the `--no-verify` option to the `git commit` command.

## Usage

See the available CLI commands:

    uv run bibra

Start up the API server and Web UI (add `--reload` for auto-reloading while developing):

    uv run bibra serve

## Security

The `extract-url` endpoints (API and CLI) fetch a user-supplied URL, which is a
classic Server-Side Request Forgery (SSRF) vector. BIBRA mitigates this with a
hardened fetch layer (`bibra/net_security.py`) that applies defense in depth:

- **Egress is off by default.** URL fetch/extraction is refused unless
  `BIBRA_URL_PROXY` is set. A configured proxy is the recommended production
  setup (a forward proxy with egress allowlists is the strongest single
  control); the special value `direct` opts into direct egress with full
  in-app validation instead.
- **Scheme allowlist.** Only `https` by default (extend with
  `BIBRA_URL_SCHEMES`).
- **Resolved-IP blocking.** The resolved destination IP is checked at connect
  time (not just the initial URL) against a table of non-public ranges —
  loopback, RFC 1918, link-local/cloud metadata (`169.254.169.254`), CGNAT,
  and reserved multicast/unique-local ranges — for both IPv4 and IPv6. This
  also covers every redirect hop, which defeats DNS-rebinding and
  redirect-based bypasses.
- **Resource limits.** A hard byte cap (`BIBRA_URL_MAX_BYTES`) and explicit
  timeouts (`BIBRA_URL_TIMEOUT`) are enforced, and redirects are bounded
  (`BIBRA_URL_MAX_REDIRECTS`).
- **Content verification.** The response `Content-Type` must be in
  `BIBRA_URL_CONTENT_TYPES` and the bytes must pass a magic-byte check before
  being handed to a backend.

These options (all `BIBRA_URL_*`) are documented in [.env.example](.env.example).

## Testing

### Python Tests

Run the Python test suite with:

    uv run pytest

### Cypress E2E Tests

Run the Cypress end-to-end tests:

**Run Cypress in interactive mode (opens Cypress GUI):**

    npx cypress open

**Run Cypress headless**

    npm run cy:run

## Use of AI Tools

This project uses AI‑powered development tools, including the [Zoo Code VSCode extension](https://www.zoocode.dev/), to support the development process. AI assistance may be used for tasks such as:

- generating and refactoring code and tests
- drafting documentation
- exploring ideas and potential solutions

All LLM‑generated content is manually reviewed and approved before being included in the project and the use of AI is disclosed via the [pull request template](.github/PULL_REQUEST_TEMPLATE.md). We indicate AI use, how much human effort went into the work and especially into verifying the result of AI using the [AI Traffic Lights Protocol](https://nlkw.de/en/blog/ai-tlp/) by Nila Löber. AI:ORANGE is the minimum level required for merging pull requests.
