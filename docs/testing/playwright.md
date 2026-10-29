# Browser tests (Playwright)

The suite in `e2e/` drives the real app in Chromium against a throwaway stack it starts
itself. It covers what only a browser shows: routing and redirects, forms, permission-gated
screens and two people acting on the same data. Rules and logic stay in pytest and Vitest
(see [test-plan.md](test-plan.md)).

## Run it

Once per checkout:

```bash
npm ci
```

```bash
npx --workspace glideship-e2e playwright install chromium
```

The backend's Python dependencies must be installed, with the dev extras (`pip install -e
"backend[dev]"`). Point `E2E_PYTHON` at that interpreter if `python` on your `PATH` isn't it.
Docker must be running.

```bash
E2E_PYTHON=/opt/anaconda3/envs/python3129/bin/python npm run test:e2e
```

Playwright starts the stack, runs every spec and stops the stack again. Useful variations,
from `e2e/`:

- One file: `npx playwright test specs/leave.spec.ts`. The setup wizard spec runs first
  every time, because it empties the database; add `--no-deps` to skip it.
- Watch it: `npx playwright test --headed`, or `--ui` for the step-through runner.
- A failure: `npx playwright show-report`, or `npx playwright show-trace <trace.zip>` from
  `test-results/`. Traces and screenshots are kept for failed tests only.

### Keep the stack up between runs

Starting the stack takes about 20 seconds. To pay that once:

```bash
E2E_PYTHON=/opt/anaconda3/envs/python3129/bin/python npm --workspace glideship-e2e run stack
```

Then, in another terminal, `npx playwright test` from `e2e/` reuses it (CI never does).
Ctrl-C stops it and removes its containers (press it twice more to stop without waiting).
The backend doesn't reload, so restart the stack after a backend change; frontend changes
reload as usual.

## What the stack is

`e2e/stack/run.ts` starts, in order:

1. Postgres (`pgvector/pgvector:pg16`) and Redis (`redis:7-alpine`) in Docker, on loopback
   ports Docker picks;
2. `alembic upgrade head`;
3. the backend, through `backend/tests/e2e_stack/serve.py`;
4. the multiplayer server;
5. the Vite dev server, last, so "the frontend answers" means everything is up. It starts
   on a cold dependency cache (`--force`), and the run fails at the end if Vite ever had
   to re-optimise and reload the app, which would also happen to someone using it.

It never touches your own stack. The frontend, backend and multiplayer ports default to
13000-15999, offset by a hash of the checkout's path so two worktrees never share a stack
(move them with `E2E_FRONTEND_PORT`, `E2E_BACKEND_PORT`, `E2E_MULTIPLAYER_PORT`). Each child
gets a short allowlist of environment variables rather than your shell's, the backend runs
from `e2e/.stack/` with its own `HOME`, so it never reads `backend/.env` or your home
directory, and all secrets are random per run. Logs are in `e2e/.stack/logs/`.

A second start in the same checkout refuses while the first is running. If a run was killed
outright, the next start removes its containers (they carry a label naming the checkout) and
stops the processes it left behind.

## Nothing leaves the machine

`serve.py` installs the same fakes as the backend integration tests (see [fakes.md](fakes.md))
before uvicorn starts:

- `ExternalCallGuard` refuses DNS and connects outside loopback, connects to the default ports
  of a developer's stack (5432, 6379, 8000, 3000, 5173, 2567) and any real `claude`, `codex` or
  `copilot` process. The backend runs on the stdlib asyncio loop, because uvloop connects in
  native code where the guard can't see it.
- `FakeEmbedder` replaces the downloaded embedding model.
- `FakeClaudeRunner` answers every agent run with a short scripted reply.

Slack, GitHub, Jira, Giphy and Google are never configured, so their code paths stay off. The
one expected refusal is the local Ollama probe in the AI settings, which reads as "not
installed".

In the browser, every context only talks to the frontend origin (the dev proxy forwards the
API and multiplayer). Other requests are aborted, except Google Fonts, which get an empty
stylesheet.

After each test, an automatic fixture fails it if any of these happened:

- a browser request or websocket tried to leave the stack;
- a page threw an uncaught error;
- the backend refused an external call;
- the fake agent CLI flagged a run.

## Writing a spec

- Import `test` and `expect` from `fixtures/test.ts`.
- Seed what the test needs with `seedOrg()` from `fixtures/stack.ts`. It takes members with
  system roles, managers, leave types, registry features and an open quiz, and returns their
  ids and credentials. Every test seeds its own org, so specs run in parallel without
  sharing data.
- Sign in with `signedIn(member)`, which goes through the real login API and returns a page in
  its own browser context. Two members means two windows in one test.
- Use `Api.as(member)` (`fixtures/api.ts`) for setup steps the test isn't about, such as
  creating the BUD whose stages it then moves.
- Find elements by role and label (`getByRole`, `getByLabel`). Nothing in the app has a
  `data-testid`; add one only when no accessible name fits. A control a test can't find by
  role is usually an accessibility bug worth fixing.
- Wait on what the user would see (`expect(...).toBeVisible()`), never a fixed sleep.

The login page signs in to the install's first org, so only the login spec seeds into that
org (`primary: true`). Everything else gets an org of its own and signs in through the API.

## CI

`.github/workflows/e2e.yml` runs the suite on every pull request with the same stack. On
failure it uploads the HTML report, the traces and the stack logs as the `playwright-report`
artifact.
