# AGENTS.md

## Dependency Management

Always use `uv` for dependency management, **not** `pip`.

## JavaScript/Node.js Dependencies

For JavaScript dependencies (e.g., Cypress for E2E testing), use `npm`:
- Install dependencies: `npm install`
- Run Cypress in interactive mode: `npm run cy:open`
- Run Cypress headless: `npm run cy:run`

JavaScript dependencies are managed via `package.json` and `node_modules`.
