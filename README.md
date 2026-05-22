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

```bash
uv sync
```

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

## Release Process
<details>
<summary>See steps:</summary>

### Normal release (minor version)

1. Make a new version with bumpversion:
    ```bash
    bump-my-version bump release
    ```
2. Check that the new version number matches your expectations:
    ```
    git show
    ```
3. Push the commit to GitHub:
    ```
    git push
    ```
4. Push the version tag too:
    ```
    git push --tags
    ```
5. Wait for [GitHub Actions jobs](https://github.com/NatLibFi/BIBRA/actions) to complete. The version tag should trigger a distribution and Docker builds that are uploaded to [PyPI](https://pypi.org/project/BIBRA/) and [Quay.io](https://quay.io/repository/natlibfi/bibra).
6. In GitHub Releases tab, turn the tag into a release and add release notes.
7. Close the [milestone](https://github.com/NatLibFi/BIBRA/milestones) corresponding to the release and create a new one for the next release.
8. Announce the release.
9. Prepare the main branch for the next development release:
    ```
    bump-my-version --no-tag minor
    ```
    (this should increment the second part of the version number and add a `-dev` suffix, but not create a new tag).
10. Check with git log that the new version number matches your expectations.
    Push the commit to GitHub:
    ```
    git push
    ```
</details>

## Use of AI Tools

This project uses AI‑powered development tools, including the [RooCode VSCode extension](https://roocode.com/), to support the development process. AI assistance may be used for tasks such as:

- generating and refactoring code
- drafting documentation
- exploring ideas and potential solutions

All AI‑generated content is manually reviewed and approved before being included in the project and the use of AI is disclosed. AI tools do not make decisions independently, as we do not consider their output to be error‑free.
