# TaskFlow QA

End-to-end test suite for [TaskFlow Web](../taskflow-web/) using Playwright and Cucumber BDD.

## Prerequisites

- **Node.js** >= 18
- **TaskFlow Web** running at `http://localhost:9002` (or set `BASE_URL`)
- **TaskFlow API** running at `http://localhost:9001` (or set `API_URL`)

See [`examples/README.md`](../README.md) for the canonical port map —
these ports are hardcoded in `taskflow-web/src/services/api.ts`, so
changing them requires updating both the app and this test suite.

## Quick Start

```bash
# Install dependencies
npm install

# Install browser binaries (first time only)
npx playwright install

# Run all tests
npm test
```

## Running Tests

```bash
# Smoke tests — quick health checks
npm run test:smoke

# End-to-end flows (login, task management)
npm run test:e2e

# Cucumber BDD tests (feature files + step definitions)
npm run test:cucumber

# Open the HTML test report
npm run report
```

## Environment Variables

| Variable   | Default                  | Description          |
|------------|--------------------------|----------------------|
| `BASE_URL` | `http://localhost:9002`  | TaskFlow Web frontend |
| `API_URL`  | `http://localhost:9001`  | TaskFlow API backend  |
| `CI`       | —                        | Enables retries (2), single worker |

## Project Structure

```
tests/
  smoke/          Quick health checks (Playwright)
  e2e/            Full end-to-end flows (Playwright)
src/
  features/       Gherkin .feature files by domain
  steps/          Step definitions matching features
  pages/          Page Object Model classes
  fixtures/       Playwright fixtures (auth setup, etc.)
  helpers/        API client, test data factories
```

## Start the App First

Before running tests, start the backend and frontend:

```bash
# Terminal 1 — TaskFlow API backend
cd ../taskflow-api
source .venv/bin/activate
uvicorn src.main:app --reload --port 9001

# Terminal 2 — TaskFlow Web frontend
cd ../taskflow-web
npm run dev -- --port 9002
```

Then run the tests from this directory.
