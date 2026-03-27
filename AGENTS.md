# AGENTS.md

## Python Dependencies

Always use `uv` for dependency management (e.g. `uv add`), **not** `pip` or `uv pip`.

## JavaScript/Node.js Dependencies

For JavaScript dependencies (e.g., Cypress for E2E testing), use `npm install`.

## Testing

**Always run tests after any code changes.**

### Python Tests

Run with verbose output: `pytest -v`

Or run specific test files: `pytest tests/test_<test_file>.py -v`

### Cypress Tests

Run Cypress E2E tests in headless mode: `npm run cy:run`

### Pre-commit Checklist

Before committing code changes, ensure:
1. ✅ Ruff linter and formatter checks pass (`ruff check` and `ruff format --check`)
2. ✅ All pytest tests pass (`pytest -v`)
3. ✅ All Cypress E2E tests pass (`npm run cy:run`)