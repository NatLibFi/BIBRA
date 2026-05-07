# AGENTS.md

## Python Dependencies

Always use `uv` for dependency management (e.g. `uv add`), **not** `pip` or `uv pip`.

## JavaScript/Node.js Dependencies

For JavaScript dependencies (e.g., Cypress for E2E testing), use `npm install`.

## Code Style

Python code style follows Ruff format. Max line length 88 chars.

## Testing

**Always run Python and Cypress tests after any code changes.**

### Python Tests

Run with verbose output: `uv run pytest -v`

Or run specific test files: `uv run pytest tests/test_<test_file>.py -v`

### Cypress Tests

Run Cypress E2E tests in headless mode: `npm run cy:run`

### Task Completion / Pre-commit Checklist

Before considering a task completed, ensure:
1. ✅ Ruff linter and formatter checks pass (`ruff check` and `ruff format --check`)
2. ✅ All pytest tests pass (`uv run pytest -v`)
3. ✅ All Cypress E2E tests pass (`npm run cy:run`)
