# AGENTS.md

## Running Commands

Do not use `cd` in front of commands, run them from the current directory as is.

## Python Dependencies

Always use `uv` for dependency management (e.g. `uv add`), **not** `pip` or `uv pip`.

## JavaScript/Node.js Dependencies

For JavaScript dependencies (e.g., Cypress for E2E testing), use `npm install`.

## Code Style

Python code style follows Ruff format. Max line length 88 chars. Imports on top of file unless there are special reasons (document reason with comment). Modules and classes must have docstrings.

## Code Quality Enforcement

**Ruff checks are a mandatory gate before claiming any task complete.** Every agentic tool invocation must run:

1. `uv run ruff check --fix` — linting (auto-fix where possible)
2. `uv run ruff format` — formatting (auto-format)
3. `uv run ty check` — type checking

Run the checks again with `uv run ruff check`, `uv run ruff format --check`, and `uv run ty check` to verify everything passes. Do **not** claim a task complete until all pass.

## Testing

**Always run Pytest and Cypress tests after any code changes.**

### Python Tests

Run with verbose output: `uv run pytest -v`

Or run specific test files: `uv run pytest tests/test_<test_file>.py -v`

### Cypress Tests

Run Cypress E2E tests in headless mode with the helper script: `bash cypress/run_cypress.sh`

### Task Completion / Pre-commit Checklist

Before considering a task completed, ensure:
1. ✅ `uv run ruff check --fix` applied and `uv run ruff check` passes
2. ✅ `uv run ruff format` applied and `uv run ruff format --check` passes
3. ✅ `uv run ty check` passes
4. ✅ All pytest tests pass (`uv run pytest -v`)
5. ✅ All Cypress E2E tests pass (`bash cypress/run_cypress.sh`)

**Note: Steps 1–3 must pass before steps 4–5. Ruff should auto-fix issues where possible; manually fix anything it can't.**
