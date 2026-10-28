# Test fakes for external services

The backend calls the Claude CLI, GitHub, Slack, Jira and a downloaded embedding model.
`backend/tests/fakes/` replaces each of them with a small, deterministic, in-process fake,
so a test can drive a real flow (HTTP route, service, repository, Postgres) end to end
without leaving the machine. Nothing here is a new dependency: the HTTP fakes are
`httpx.MockTransport` handlers and the rest is plain pytest and `unittest.mock`-style
monkeypatching.

## Using the fakes in a new test directory

Fixtures are plain functions in `tests/fakes/fixtures.py` (no database) and
`tests/fakes/fixtures_db.py` (integration database). Re-export the ones you need from
the directory's `conftest.py`:

```python
from tests.fakes.fixtures import external_guard, fake_claude, fake_embeddings, fake_slack
from tests.fakes.fixtures_db import app_sessions, mcp_claude

__all__ = ["app_sessions", "external_guard", "fake_claude", "fake_embeddings", "fake_slack", "mcp_claude"]
```

Re-exporting `external_guard` and `fake_embeddings` turns them on for every test in the
directory (they are autouse). `fixtures_db` needs `pg_session_factory` and `client` from
`tests/integration/conftest.py`, so only use it under `tests/integration/`.

## The guard: no test reaches the outside world

`external_guard` (`tests/fakes/guard.py`) patches the doors out of the process for one
test:

- DNS lookups and socket connects to anything but loopback are refused. Unix sockets (the
  Docker daemon) are allowed, so the testcontainers Postgres still works.
- Loopback connects to the local services named in the app settings (database, Redis,
  backend, frontend, multiplayer) and to Ollama's port are refused, so a stray
  `AsyncSessionLocal()` or HTTP call can never reach your dev stack. `guard.allow_port(n)`
  lets one through.
- Any command line that runs `claude`, `codex` or `copilot` is refused, wherever the binary
  appears in it (`sandbox-exec ... claude`, `env X=1 codex`, shell strings). `git` still
  runs, with `GIT_ALLOW_PROTOCOL=file`, so it can only talk to local repositories.
- `BODHIORCHARD_HYBRID_SANDBOX` and `BODHI_MOCK_PR_FILES_PATH` are cleared, so neither the
  macOS agent sandbox nor the PR-files mock file can route around the fakes.
- `get_redis()` answers `None`, so every Redis user takes its fail-open path (the MCP rate
  limiter included).
- Background tasks the test started are awaited (up to 5 s), then cancelled, before the
  patches come off.

Each refusal raises in the caller (the code sees a failed connection) and is recorded; the
test fails at teardown if anything was recorded, even when the code swallowed the error.

`http_router` gives every `httpx.AsyncClient` / `httpx.Client` created without an
explicit transport a `MockTransport` that routes by host to the mounted fakes. An unmounted
host is a guard violation. Clients that pass their own transport (the tests' ASGI clients)
are untouched.

## FakeClaudeRunner

`fake_claude` fakes the agent CLI at the subprocess spawn. Every agent run in the app ends
in `claude_runner.run_claude_code`, which builds the real command line (prompt,
`--mcp-config`, `--allowedTools`, filtered env) and spawns `claude`. The fake intercepts
that spawn, records an `AgentRun`, runs the script, and returns a fake process whose stdout
is shaped like the real CLI's (`--output-format json` or `stream-json`). The runner's own
parsing, error mapping and progress callbacks therefore run unchanged.

A script says what the agent does:

```python
from tests.fakes.claude_script import AgentScript, Say, ToolCall

script = AgentScript.ok(
    "# Spec\n\nThe document the agent returns.",
    Say("Reading the BUD first."),
    ToolCall("get_bud_context", {"limit": 5}),
    ToolCall("write_bud", lambda run: {"bud_number": 1, "content": run.prompt[:20]}),
)
```

`ToolCall` params can be a callable that receives the run so far (prompt, earlier tool
results), for ids that only exist at runtime. Tool calls are executed for real: the fake
POSTs to `/mcp/tools/{name}` with the token from the run's MCP config, exactly as the stdio
bridge does. With `mcp_claude` that request goes through the app's MCP route on the test
database, so the call is authenticated, audited and persisted like a real one (rate limiting
fails open, because Redis is off). If the route itself crashes, the call is recorded as a 500
(what the bridge reports) and the test fails at teardown. All tool calls of a run happen when
the process is spawned, before the runner reads any output.
A tool outside the run's `BODHIORCHARD_MCP_TOOLS` or `--allowedTools` list is refused
without a request, as the CLI would.

Choosing a script for a run:

- `fake_claude.when("write_synthesis_feature", script)`: when the prompt contains the text
  (or pass a callable that takes the `AgentRun`);
- `fake_claude.enqueue(s1, s2)`: in order, for runs no rule matched;
- `fake_claude.default = script`: anything else.

A run with no script exits non-zero and fails the test at teardown. So does a command line
the real CLI would reject (`stream-json` without `--verbose`, an empty prompt, an MCP config
that does not launch the bridge script or lacks a backend URL or token) and a `ToolCall`
params callable that raises. A `claude --version` probe is answered without using a script.

Failure modes, all through the real runner:

| Script | What the runner sees | Result |
| --- | --- | --- |
| `AgentScript.timeout(*steps)` | steps run, then the process hangs until killed | `TIMEOUT`, process killed |
| `AgentScript.crash(2, "boom")` | exit 2, stderr `boom`, no result event | `UNKNOWN`, "exit code 2; boom" |
| `AgentScript.malformed("{oops")` | exit 0, stdout is not JSON | success, raw stdout as output |
| `AgentScript.max_turns()` | result event with `error_max_turns` | `MAX_TURNS` |
| `script.with_insight()` | a `★ Insight` block before the result | success, contaminated output |
| `script.with_preamble()` | chatty framing before the document | success, framed output |
| `AgentScript.ok("x")` | no tool calls at all | success, nothing written |
| `ToolCall` to a failing tool | MCP answers `{"error": ...}` or 4xx | `ToolCallRecord.is_error` |

A hanging script is only ended by the runner's own `asyncio.wait_for`, so give the run a
small timeout (`ClaudeRunnerConfig(timeout_seconds=1)`, or `seed_org(config={"scan":
{"timeout_seconds": 1}})` for scans); a runner that lost its deadline would hang the test.

For assertions: `fake_claude.runs` (each `AgentRun` has `prompt`, `argv`, `flag()`, `env`,
`mcp_token`, `mcp_tools`, `tool_calls`, `killed`) and `fake_claude.tool_calls("name")`.

## FakeGitHub

`fake_github` is an in-memory `api.github.com` for one App installation:

- the App JWT to installation-token exchange and the repo to installation lookup (both
  need an App JWT whose signature is checked against the fake App's RSA key, so a wrong key
  or app id is refused; `FakeGitHub(key_pair=new_key_pair())` gives an App its own key);
- installable repos, branches, PR commits and PR files, paginated like GitHub: `per_page`
  (default 30) up to `max_page_size` (100), with a `Link: rel="next"` header. Lower
  `max_page_size` to force several pages for callers that follow `Link`;
- pull requests: list filtered by `state`, `base` and `head` (`owner:branch`), create
  (a second open PR for the same head answers 422), reviews;
- org members and user profiles. Every reply's `(path, status)` is kept in `responses`.

Installation-token routes need a token the fake issued (or one added to `extra_tokens`
for PAT callers). `fake_github.fail(method, path_regex, 401 | 404 | 500)` and
`fake_github.rate_limit(method, path_regex)` queue error replies.

`seed_org(factory, github=fake_github)` stores the fake App's id, encrypted private key and
installation id on a new org. Webhook deliveries are built with
`tests.fakes.github_payloads` (`pull_request_event`, `installation_event`) and signed with
`tests.fakes.signing.signed_github_webhook(secret, event, payload)`; sign with another
secret for the negative case.

## FakeSlack

`fake_slack` is an in-memory `slack.com/api` for one workspace. Every Web API call is
recorded as a `SlackCall(method, args, token)`; `posted_texts()` and `calls_to(method)` help
assertions. It answers `chat.postMessage` (threads are kept, so `conversations.replies`
returns them), `chat.update`, `chat.postEphemeral`, `reactions.add/remove`, `users.info`,
`users.list`, `users.getPresence`, `users.profile.get/set`, `conversations.open`,
`conversations.history`, `views.open`, `auth.test`, `auth.revoke` and `oauth.v2.access`
(any code but `bad-code` returns a user token). A call with no token answers `not_authed`;
a token that is not `xox…`-shaped, or was revoked, answers `invalid_auth`. Profiles and
statuses are kept per token. Add people with `add_user(id, name, email)`. `fail(method, "missing_scope")` and `rate_limit(method)`
(HTTP 429 `ratelimited`, `Retry-After: 0`) queue errors.

Inbound requests are signed like Slack signs them: `signed_slack_event`,
`signed_slack_interaction` and `signed_slack_command` in `tests.fakes.signing`. Pass
`timestamp=` for a stale request. `seed_org(factory, slack=fake_slack)` stores the matching
team id, bot token and signing secret.

## FakeJira

`fake_jira` is an in-memory Jira Cloud site on `*.atlassian.net`. Requests must carry the
fake's Basic credentials (`email`, `api_token`), otherwise 401. It serves `serverInfo`,
project search, project statuses, single issues, the field list and `/search/jql` with
`nextPageToken` pagination (`page_size`, default 2) filtered on `project = KEY`. Build
issues with `jira_issue(key, summary, ...)`. `fail(path_regex, 401 | 403 | 429 | 500)`
queues errors; 429 carries `Retry-After: 0`. Note that `JiraClient.search_issues` sleeps a
second between pages, so keep paginated tests to a page or two.

## Embeddings

`fake_embeddings` replaces the methods of the shared `embedding_service` with a
hash-seeded 384-dimension unit vector: the same text always gives the same vector, so
pgvector queries behave. `pin(phrase, vector)` fixes the vector for any text containing a
phrase (for distance-threshold tests) and `failing = True` makes every call raise.

## Local git repositories

`git_repo` builds, under `tmp_path`, a bare `origin` and a clone of a small three-module
Python service (`shop/orders`, `shop/billing`, `shop/accounts`) with `main` and `develop`
pushed. Commits use a fixed author and date and ignore your global git config, so the same
tree always has the same SHAs. `repo.commit({"path": "text"}, "message", branch="main")`
adds and pushes a commit; `repo.head("main")` reads `origin/main`. `git_repo_factory(name)`
builds more. The real indexer, worktrees and `git fetch origin` all work against it.

Every commit is authored by `fixture.dev@example.test` unless you pass `author_email=`. A scan
turns git authors into members of the scanning org and an email is unique across orgs, so a
test that scans in more than one org should give each repo its own author.

## App state helpers

- `app_sessions` (integration): rebinds `AsyncSessionLocal` in every app module to the
  test database, so background work (scan fanout, MCP audit rows, job handlers) writes
  there. It imports every app module first so none binds the real factory later.
- `data_dir`: points `settings.storage.data_dir` (clones, scan worktrees, uploads) at
  `tmp_path`.
- `event_recorder`: records every `event_bus.publish(topic, data)`; call `await
  recorder.settle()` before asserting.
- `tests.fakes.seed`: `seed_org` (optionally wired to the fake GitHub / Slack, with an org
  `config`), `seed_member`, `seed_repo`, `auth_headers`. Seeded emails use the reserved
  `example.test` domain.

## Example: a scripted agent writing through MCP

The end-to-end scan tests (`tests/integration/scan_e2e/`, added on top of this package) do
this; `synthesis_writing` and `start_scan_over_http` come from their `scan_support.py`.

```python
pytestmark = pytest.mark.integration


async def test_synthesis_writes_features(
    client: AsyncClient, app_sessions: Factory, mcp_claude: FakeClaudeRunner,
    git_repo: LocalGitRepo, data_dir: Path,
) -> None:
    org = await seed_org(app_sessions)
    repo_id = await seed_repo(app_sessions, org.org_id, git_repo)
    mcp_claude.when("write_synthesis_feature", synthesis_writing(2))

    scan_id = await start_scan_over_http(client, auth_headers(org.owner_id, org.org_id), repo_id)

    assert [c.status_code for c in mcp_claude.tool_calls("write_synthesis_feature")] == [200, 200]
```

## Running the suites

```bash
cd backend
python -m pytest tests/fakes_selftest                      # the fakes' own tests, no Docker
python -m pytest -m integration tests/integration/scan_e2e # needs Docker
```

On Docker Desktop for macOS export `DOCKER_HOST=unix://$HOME/.docker/run/docker.sock` and
`TESTCONTAINERS_RYUK_DISABLED=true` first. Slow tests carry the `slow` marker; skip them
with `-m "integration and not slow"`.

## What the fakes do not cover

- Codex, Copilot and Ollama providers: only the Claude CLI spawn is faked. An org set to
  another provider hits the guard (the CLI spawn or Ollama's port is refused).
- Timing between tool calls and output: all tool calls run at spawn, so a test cannot cancel
  an agent between two of its MCP writes.
- The real MCP stdio bridge process: the fake makes the same HTTP call the bridge makes,
  but the bridge's JSON-RPC framing itself is not exercised.
- Google Calendar and Giphy have no fake yet; mount one on `http_router` the same way.
