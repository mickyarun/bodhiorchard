# TaskFlow QA — Test Automation Project

## Purpose

Playwright + Cucumber test suite for the TaskFlow web application (`examples/taskflow-web`).

## Tech Stack

- **Playwright** for browser automation
- **Cucumber** (Gherkin BDD) for feature files and step definitions
- **TypeScript** for all code
- **Page Object Model** for maintainable selectors

## Project Structure

```
src/
  features/     Gherkin .feature files organized by domain
  steps/        Step definitions (TypeScript) matching feature files
  pages/        Page Object Model classes (one per page/screen)
  fixtures/     Playwright fixtures for auth, setup, etc.
  helpers/      Shared utilities (API client, test data generators)
tests/          Pure Playwright spec tests (non-Cucumber)
  smoke/        Quick health checks
  e2e/          Full end-to-end flows
```

## Conventions

1. **Page Objects**: One class per page, encapsulates all selectors and actions. Import via `@pages/PageName`.
2. **Feature files**: Use descriptive scenario names. One feature per file, grouped by domain.
3. **Step definitions**: Keep steps reusable. Use `Given/When/Then` consistently.
4. **Test data**: Use `helpers/test-data.ts` factories. Never hardcode test data in steps.
5. **API setup/teardown**: Use `helpers/api-client.ts` for pre/post-test data via REST.

## Running Tests

```bash
npm install
npx playwright install

# Run all Playwright tests
npm test

# Run smoke tests only
npm run test:smoke

# Run Cucumber BDD tests
npm run test:cucumber

# Open HTML report
npm run report
```

## Environment

- `BASE_URL`: Frontend URL (default: `http://localhost:5173`)
- `API_URL`: Backend API URL (default: `http://localhost:8000`)
