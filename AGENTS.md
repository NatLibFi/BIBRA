# AGENTS.md

## Python Dependencies

Always use `uv` for dependency management (e.g. `uv add`), **not** `pip` or `uv pip`.

## JavaScript/Node.js Dependencies

For JavaScript dependencies (e.g., Cypress for E2E testing), use `npm`:
- Install dependencies: `npm install`
- Run Cypress in interactive mode: `npm run cy:open`
- Run Cypress headless: `npm run cy:run`

JavaScript dependencies are managed via `package.json` and `node_modules`.

## Testing

**Always run tests after any code changes.**

### Python Tests

Run with verbose output: `pytest -v`

Or run specific test files: `pytest tests/test_<test_file>.py -v`

### Cypress Tests

Run Cypress E2E tests in headless mode: `npm run cy:run`

### Pre-commit Checklist

Before committing code changes, ensure:
1. ✅ All pytest tests pass (`pytest -v`)
2. ✅ All Cypress E2E tests pass (`npm run cy:run`)
