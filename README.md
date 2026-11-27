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

### Evaluate predictions

Compare extracted metadata with ground truth using
[bibraeval](https://pypi.org/project/bibraeval/), installed with BIBRA:

```bash
> bibra eval \
  --ground-truth GOLD-STANDARD \
  --predictions SOME-BIBRA-OUTPUT \
  --results-dir metrics/
```

shape: (3, 4)
┌────────┬───────────┬──────────┬───────────┐
│ metric ┆ mode      ┆ value    ┆ support   │
│ ---    ┆ ---       ┆ ---      ┆ ---       │
│ str    ┆ str       ┆ f64      ┆ f64       │
╞════════╪═══════════╪══════════╪═══════════╡
│ f1     ┆ field-avg ┆ 0.183378 ┆ 30.083333 │
│ prec   ┆ field-avg ┆ 0.209394 ┆ 25.083333 │
│ rec    ┆ field-avg ┆ 0.236272 ┆ 25.0      │
└────────┴───────────┴──────────┴───────────┘

Both inputs accept directories of JSON metadata objects (filename stems are
document IDs) or JSONL files. Each JSONL line must wrap the metadata in a
`record` object with a non-empty `doc_id`, for example:

```json
{"doc_id": "book-1", "record": {"title": "Example", "year": "2026"}}
```

Records are validated against BIBRA's `PublicationMetadata` schema. By default,
all schema fields use exact matching with weight 1 and aggregation uses
`field-avg`, matching Evaluator's defaults. Use `--mode doc-avg` or
`--mode micro-avg` to change aggregation. Document ID mismatches are errors;
`--drop-mismatched-doc-ids` explicitly evaluates only shared IDs.

The command prints a summary table with `metric`, `mode`, `value`,
and `support`. To save bibraeval's detailed outputs:

    uv run bibra eval --ground-truth gold.jsonl --predictions predictions.jsonl \
        --field-metric-config metrics.yaml --mode doc-avg --results-dir results/

`--results-dir` writes `summary_metrics.yaml`, `comparison_matrix.csv`, and
`intermediate_results.csv` (the last is omitted for `micro-avg`).
`--field-metric-config` (also accepted as `--field_metric_config`) loads a flat
YAML field mapping or one nested under `fields`. When configured, only listed
fields are scored; use output JSON field names, such as `e-isbn`, for aliased fields.
For example:

```yaml
title:
  metric: Levenshtein
  match_threshold: 0.5
  weight: 2.0
year:
  metric: Exact
  weight: 1.0
```

Levenshtein requires `match_threshold` between 0 and 1 for list alignment;
Exact does not accept it. Weights must be positive.

## Security

The `extract-url` endpoints (API and CLI) fetch a user-supplied URL, which is a
classic Server-Side Request Forgery (SSRF) vector. BIBRA mitigates this with a
hardened fetch layer (`bibra/net_security.py`) that applies defense in depth:

- **Egress is off by default (API).** The REST API refuses URL
  fetch/extraction unless `BIBRA_URL_PROXY` is set. A configured proxy is the
  recommended production setup (a forward proxy with egress allowlists is the
  strongest single control); the special value `direct` opts into direct
  egress with full in-app validation instead.
- **CLI fallback.** The CLI is intentionally more lenient for local one-off
  use: when `BIBRA_URL_PROXY` is unset, `extract-url` behaves as if it were
  set to `direct` (fetches directly, still with full in-app validation).
  Set `BIBRA_URL_PROXY` to a proxy URL to route CLI downloads through a
  proxy.
- **No ambient proxy hijacking.** The fetch layer ignores `HTTP_PROXY`,
  `HTTPS_PROXY` and `NO_PROXY` environment variables: the only egress route
  ever in effect is the explicit `BIBRA_URL_PROXY` (if one is configured).
  Note that the proxy URL itself is operator-trusted and not validated by
  BIBRA.
- **Scheme allowlist.** Only `https` by default (extend with
  `BIBRA_URL_SCHEMES`).
- **Resolved-IP blocking (direct mode).** In `direct` mode, the hostname
  is resolved and every resolved address is checked against a table of
  non-public ranges — loopback, RFC 1918, link-local/cloud metadata
  (`169.254.169.254`), CGNAT, and reserved multicast/unique-local ranges —
  for both IPv4 and IPv6, not just for the initial URL: the check is
  re-applied on every redirect hop, defeating redirect-based bypasses.
  In proxy mode this check is skipped: the proxy's own egress allowlist
  is the authoritative control, and local DNS results may not match the
  proxy's resolver.
  *Known limitation:* the check resolves the hostname once and the HTTP
  transport then resolves it again when dialing the socket, leaving a
  small TOCTOU window that an actively rebinding DNS resolver could
  exploit in `direct` mode. The check therefore mitigates, but does not
  fully eliminate, DNS rebinding; the full protection is provided by
  routing egress through a proxy.
- **Resource limits.** A hard byte cap (`BIBRA_URL_MAX_BYTES`) and explicit
  timeouts (`BIBRA_URL_TIMEOUT`) are enforced — each connect/read/write
  operation is bounded, and the same value is also the total deadline for
  the complete download, so a server that drips small chunks to evade the
  per-read timeout cannot hold a request open indefinitely. Redirects are
  bounded (`BIBRA_URL_MAX_REDIRECTS`).
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
