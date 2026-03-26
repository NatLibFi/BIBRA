// Load Cypress environment variables
import './commands';

// Global setup for E2E tests
Cypress.config('baseUrl', 'http://localhost:8000');
