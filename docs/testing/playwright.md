# Browser tests (Playwright)

The suite in `e2e/` drives the real app in Chromium, against a throwaway stack it starts
itself. It covers what only a browser can show:

- routing and redirects;
- forms;
- permission-gated screens;
- two people acting on the same data;
- phone layouts;
- automated accessibility checks.

Rules and logic stay in pytest and Vitest (see [test-plan.md](test-plan.md)).

## Run it

Once per checkout:

```bash
npm ci
```

```bash
npx --workspace glideship-e2e playwright install chromium
```

You also need:

- the backend's Python dependencies, with the dev extras: `pip install -e "backend[dev]"`;
- `E2E_PYTHON` pointing at that interpreter, if `python` on your `PATH` isn't it;
- Docker running.

```bash
E2E_PYTHON=/opt/anaconda3/envs/python3129/bin/python npm run test:e2e
```

Playwright starts the stack, runs every spec and stops the stack again. Useful variations,
run from `e2e/`:

- One file: `npx playwright test specs/leave.spec.ts`. Any spec runs on its own.
- One project: `--project=chromium`, `--project=mobile` or `--project=setup-wizard`.
- Watch it: `npx playwright test --headed`, or `--ui` for the step-through runner.
- A failure: `npx playwright show-report`, or `npx playwright show-trace <trace.zip>` from
  `test-results/`. Traces and screenshots are kept for failed tests only.

### Keep the stack up between runs

Starting the stack takes about 20 seconds. To pay that only once:

```bash
E2E_PYTHON=/opt/anaconda3/envs/python3129/bin/python npm --workspace glideship-e2e run stack
```

Then, in another terminal, `npx playwright test` from `e2e/` reuses it (CI never does).

- Ctrl-C stops it and removes its containers. Press it twice more to stop without waiting.
- The backends don't reload, so restart the stack after a backend change.
- Frontend changes reload as usual.

## What the stack is

`e2e/stack/run.ts` starts, in order:

1. Postgres (`pgvector/pgvector:pg16`) and Redis (`redis:7-alpine`) in Docker, on loopback ports
   Docker picks.
2. `alembic upgrade head` on two databases.
3. Two backends through `backend/tests/e2e_stack/serve.py`:
   - `main` serves every spec;
   - `wizard` serves only the setup wizard, which needs an empty database. Giving it its own
     backend means no spec waits for it.
4. The multiplayer server.
5. A Vite dev server in front of each backend. The main one starts last, so "the main frontend
   answers" means everything is up. Each Vite has its own dependency cache under `.stack/`, so a
   dev server running in the same checkout is never touched. Each starts on a cold cache
   (`--force`), and the run fails at the end if Vite ever had to re-optimise and reload the app,
   which would also happen to someone using it.

It never touches your own stack:

- The e2e ports default to 13000, 14000, 15000, 16000 and 17000. Each is offset by a hash of the
  checkout's path, so two worktrees never share a stack. Move them with `E2E_FRONTEND_PORT`,
  `E2E_BACKEND_PORT`, `E2E_MULTIPLAYER_PORT`, `E2E_WIZARD_FRONTEND_PORT` and
  `E2E_WIZARD_BACKEND_PORT`.
- Each child process gets a short allowlist of environment variables, not your shell's.
- The backends run from `e2e/.stack/` with their own `HOME`, so they never read `backend/.env` or
  your home directory.
- Secrets are random for each run.
- Logs are in `e2e/.stack/logs/`.

A second start in the same checkout refuses while the first is running. If a run was killed
outright, the next start removes its containers (they carry a label naming the checkout) and
stops the processes it left behind. Global setup checks that each backend belongs to this
checkout before any test runs. It also creates the main stack's first org, which the login page
signs in to.

## Nothing leaves the machine

Before uvicorn starts, `serve.py` installs the same fakes as the backend integration tests (see
[fakes.md](fakes.md)):

- `ExternalCallGuard` refuses:
  - DNS and connects outside loopback;
  - connects to the default ports of a developer's stack (5432, 6379, 8000, 3000, 5173, 2567);
  - any real `claude`, `codex` or `copilot` process.
- `FakeEmbedder` replaces the downloaded embedding model.
- `FakeClaudeRunner` answers every agent run with a short scripted reply.

The backends run on the stdlib asyncio loop. uvloop connects in native code, where the guard
can't see it. Slack, GitHub, Jira, Giphy and Google are never configured, so their code paths stay
off. The one expected refusal is the local Ollama probe in the AI settings, which reads as "not
installed".

Every request carries an `x-e2e-test` header with the test's id. Through it, each refusal is
tagged with the test whose request caused it, including background work that request started, and
thread-pool work such as DNS lookups.

After each test, an automatic fixture fails it if any of these happened:

- a browser request or websocket tried to leave the stack;
- a page threw an uncaught error;
- the backend refused something while serving that test.

At the end of the run, global teardown fails if anything was refused at all, including work no
test started, such as job workers and scheduler loops.

In the browser, every context talks only to its stack's frontend origin; the dev proxy forwards
the API and multiplayer. Other requests are aborted, except Google Fonts, which get an empty
stylesheet.

## Writing a spec

```ts
import { createBud } from '../fixtures/api.ts'
import { expect, test } from '../fixtures/test.ts'
import { expectSection, moveBudTo } from '../screens/buds.ts'

test('a BUD moves to design', async ({ signedIn, stack }) => {
  const org = await stack.seedOrg({ members: [{ key: 'pm', role: 'pm' }] })
  const bud = await createBud(await stack.api(org.members.pm), 'Rate limit the API')
  const page = await signedIn(org.members.pm)
  await page.goto(`/buds/${bud.id}`)
  await moveBudTo(page, 'Design', 'Design')
})
```

- **Fixtures.** Import `test` and `expect` from `fixtures/test.ts`.
- **Data.** `stack` (`fixtures/client.ts`) seeds data for this test only:
  - `seedOrg()` creates an org with members, system roles, managers and leave types;
  - `addFeatures()` and `openQuiz()` add content to that org.

  A new area adds a small seed route (`backend/tests/e2e_stack/routes_seed.py`) rather than
  more fields on the org. Every test seeds its own org, so specs run in parallel without sharing
  data. Only the login tests use the install's first org (`primary: true`), because the login
  page signs in to it.
- **Signing in.** `signedIn(member)` opens a page in its own browser context, already signed in
  with tokens the seed route minted. Two members means two windows in one test.
- **The API.** `stack.api(member)` is the app's real API, for setup steps the test isn't about.
  The helpers in `fixtures/api.ts` (`createBud`, `requestLeave`, `approveLeave`) take it.
- **Screens.** Shared steps and locators live in `screens/`: the shell, login, BUDs, leave and
  the accessibility check. Put a step there once a second spec needs it.
- **Locators.** Find elements by role and label (`getByRole`, `getByLabel`), with `exact: true`
  when a name could match a longer one. Nothing in the app has a `data-testid`; add one only
  when no accessible name fits. A control a test can't find by role is usually an accessibility
  bug worth fixing.
- **Waiting.** Wait on what the user would see (`expect(...).toBeVisible()`), never a fixed
  sleep.
- **Phone layouts.** Tag phone tests `@mobile`, by putting them in
  `test.describe('...', { tag: '@mobile' }, ...)`. The `mobile` project runs them on a Pixel 7
  profile, and the desktop project skips them.
- **Accessibility.** `expectAccessible(page, name)` (`screens/a11y.ts`) runs axe-core's
  WCAG 2.1 A and AA rules and fails on serious or critical findings. Add a screen to
  `specs/accessibility.spec.ts` once it has a stable heading to wait for.

## CI

`.github/workflows/e2e.yml` runs on every pull request. The shared setup is in
`.github/actions/e2e-setup`, which caches Chromium keyed on the lockfile.

- **`playwright`** runs:
  - the whole suite;
  - `tsc` on `e2e/`;
  - `mypy --strict` on `backend/tests/e2e_stack`.

  Its matrix has one shard. To split the suite, list `1/2` and `2/2`; each shard starts its own
  stack.
- **`playwright burn-in`** runs only the specs a pull request adds or changes, three times
  each, so a flaky new test shows up in its own pull request.

On failure, both jobs upload the HTML report, the traces and the stack logs as an artifact.
