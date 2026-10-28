# Release test plan

This plan maps every feature area of Glideship to the tests that cover it: the positive
paths, the negative paths (bad input, missing permission, wrong org, wrong state), the corner
cases, the tests that already existed before this effort, and the gaps that remain. Each area
section ends with a coverage matrix.

## How to run the suites

| Suite | Command (from the directory shown) | Needs |
| --- | --- | --- |
| Backend unit | `backend/`: `python -m pytest` | nothing (integration tests are deselected by default) |
| Backend integration | `backend/`: `python -m pytest -m integration` | Docker (testcontainers starts `pgvector/pgvector:pg16`) |
| Backend lint and types | `backend/`: `ruff check . && ruff format --check . && mypy --strict app/` | |
| Frontend | `frontend/`: `npx vue-tsc --noEmit && npx vitest run` | `npm ci` at the repo root |
| Multiplayer | `multiplayer/`: `npm test` | `npm ci` at the repo root |
| CLI | `cli/`: `npm ci && npm test && npm run typecheck` | |

On Docker Desktop for macOS the Python Docker SDK may not find the socket. Export
`DOCKER_HOST=unix://$HOME/.docker/run/docker.sock`, `TESTCONTAINERS_RYUK_DISABLED=true` and
`TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE=/var/run/docker.sock` before the integration run.

Every test under `backend/tests/integration/` is marked `integration` by that directory's
conftest, so a module can't run in the Docker-free pass by accident.

## Principles

- External services are never called: the Claude, Codex and Copilot subprocesses, Ollama,
  Slack, GitHub, Google Calendar, Giphy and Jira are all mocked or stubbed.
- Repository and API behaviour is tested against real Postgres (with pgvector); pure rules are
  unit tested.
- Tests inject "today" and "now" instead of reading the wall clock.
- Integration tests share one database per session, so each test creates its own org, users
  and ids.

## Known flaky test

`backend/tests/integration/test_bud_design_upsert_concurrency.py` exercises a known race that
can create a duplicate BUD design row. A fix was proposed and declined, so the test is kept
as is: its assertion must not be weakened. It passed in the baseline run for this plan, but
expect occasional failures.

## Coverage at a glance

Counts are new test files and new test definitions added by each area's branch (parametrised
cases and `it.each` rows count once). Baseline before this work: 3,315 backend unit tests,
238 backend integration tests (plus 10 integration tests that were not marked), 867 frontend
tests, 160 multiplayer tests and 27 CLI tests.

| Area | Positive | Negative | Corner cases | New files | New tests | Bugs fixed | Test PR | Fix PRs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Auth, JWT, RBAC, org isolation | yes | yes | yes | 9 | 36 | 2 | [#420](https://github.com/mickyarun/glideship/pull/420) | [#417](https://github.com/mickyarun/glideship/pull/417), [#418](https://github.com/mickyarun/glideship/pull/418) |
| Setup wizard, repos, settings, Jira, design systems | yes | yes | yes | 15 | 98 | 5 | [#421](https://github.com/mickyarun/glideship/pull/421) | [#403](https://github.com/mickyarun/glideship/pull/403), [#404](https://github.com/mickyarun/glideship/pull/404), [#405](https://github.com/mickyarun/glideship/pull/405), [#406](https://github.com/mickyarun/glideship/pull/406), [#407](https://github.com/mickyarun/glideship/pull/407) |
| BUD lifecycle | yes | yes | yes | 17 | 83 | 4 | [#436](https://github.com/mickyarun/glideship/pull/436) | [#427](https://github.com/mickyarun/glideship/pull/427), [#428](https://github.com/mickyarun/glideship/pull/428), [#429](https://github.com/mickyarun/glideship/pull/429), [#430](https://github.com/mickyarun/glideship/pull/430) |
| Agents, jobs, MCP server | yes | yes | yes | 18 | 93 | 4 | [#422](https://github.com/mickyarun/glideship/pull/422) | [#408](https://github.com/mickyarun/glideship/pull/408), [#409](https://github.com/mickyarun/glideship/pull/409), [#410](https://github.com/mickyarun/glideship/pull/410), [#411](https://github.com/mickyarun/glideship/pull/411) |
| Repo scanning, features, bugs, triage, Slack intake | yes | yes | yes | 19 | 122 | 5 | [#437](https://github.com/mickyarun/glideship/pull/437) | [#431](https://github.com/mickyarun/glideship/pull/431), [#432](https://github.com/mickyarun/glideship/pull/432), [#433](https://github.com/mickyarun/glideship/pull/433), [#434](https://github.com/mickyarun/glideship/pull/434), [#435](https://github.com/mickyarun/glideship/pull/435) |
| People and leave | yes | yes | yes | 16 | 69 | 0 | [#423](https://github.com/mickyarun/glideship/pull/423) | none |
| Employee records and gamification | yes | yes | yes | 9 | 55 | 5 | [#424](https://github.com/mickyarun/glideship/pull/424) | [#412](https://github.com/mickyarun/glideship/pull/412), [#413](https://github.com/mickyarun/glideship/pull/413), [#414](https://github.com/mickyarun/glideship/pull/414), [#415](https://github.com/mickyarun/glideship/pull/415), [#416](https://github.com/mickyarun/glideship/pull/416) |
| Frontend (Vitest) | yes | yes | yes | 21 | 186 | 5 | [#425](https://github.com/mickyarun/glideship/pull/425) | [#393](https://github.com/mickyarun/glideship/pull/393), [#394](https://github.com/mickyarun/glideship/pull/394), [#395](https://github.com/mickyarun/glideship/pull/395), [#396](https://github.com/mickyarun/glideship/pull/396), [#397](https://github.com/mickyarun/glideship/pull/397) |
| Multiplayer, shared world, CLI | yes | yes | yes | 17 | 156 | 5 | [#426](https://github.com/mickyarun/glideship/pull/426) | [#398](https://github.com/mickyarun/glideship/pull/398), [#399](https://github.com/mickyarun/glideship/pull/399), [#400](https://github.com/mickyarun/glideship/pull/400), [#401](https://github.com/mickyarun/glideship/pull/401), [#402](https://github.com/mickyarun/glideship/pull/402) |

With every test branch and fix merged together, all gates pass: ruff, ruff format and
`mypy --strict app/`; 3,560 backend unit tests; 852 backend integration tests on Postgres;
1,243 frontend tests with `vue-tsc` clean; 309 multiplayer tests; 77 CLI tests with the CLI
type check clean. The backend suites were also run against the newest dependency versions
the `pyproject.toml` ranges allow (what CI installs), with the same result apart from the
known flaky test described above, which failed once in that run and passed in the next.

The test-suite fix that marks every integration module is [#419](https://github.com/mickyarun/glideship/pull/419), and this plan is [#438](https://github.com/mickyarun/glideship/pull/438).

### Merge order

The test PRs don't depend on any fix PR: each test branch passes on main without the fixes,
and each regression test lives in its own fix PR. Every PR branch merges cleanly with main and
with every other PR branch (checked pairwise with `git merge-tree`), so they can land in any
order.

## Areas

### Auth, JWT, RBAC and org isolation

Branch `test/auth-tenancy` (from origin/main c4303ebd).

#### Map

- Auth: `api/v1/auth.py` (login by org slug + email + password, refresh, change-password, /auth/me),
  `core/security.py` (HS JWT, `type` claim access/refresh, bcrypt 72-byte), `core/auth_deps.py`
  (`_authenticate`: token -> active user -> membership in token's org; `must_change_password`
  blocks everything but change-password), `employee_login.py` (HR generates/resets a login).
- `models/jwt_token.py` (JWTToken) exists but nothing reads or writes it: there is no
  revocation, no logout, and a password change does not end existing sessions.
- No login rate limit or lockout exists (only `public.py` bud-check has an IP limiter).
- RBAC: `permission_deps.py` (`PermissionSet`, owner bypass only for the SYSTEM `org_owner`
  role, `require_permissions` all/any), `role_defs.py`, `role_grants.py` (grant ceiling),
  `role_validation.py`, `api/v1/roles.py`, `api/v1/members.py`.
- Tenancy: `BaseRepository` scopes by `org_id` when constructed with it; `UserRepository`
  is unscoped (users are global, membership is `org_to_user`). Handlers scope by
  `current_user.org_id`.

#### Features

##### Login / refresh / change-password / me (HTTP, real Postgres)
- Positive: login returns access + refresh, `expires_in`, `must_change_password`; /auth/me
  returns org, role and permissions; refresh returns a working new pair.
- Negative: wrong password, unknown org slug, valid user but another org's slug, inactive
  user -> all the same generic 401; refresh with an access token, with a garbage token, after
  deactivation, after the membership is gone -> 401; refresh token used as bearer -> 401.
- Corner: email case/whitespace, `must_change_password` gate (403 everywhere, change-password
  allowed, then access restored, old password stops working), password over 72 bytes.
- Existing: `tests/core/test_auth_hardening.py` (unit: token typing, deactivation mock,
  production secret), `test_security_bcrypt_limit.py`, `integration/test_employee_login.py`
  (HR generate/reset).
- Gap: no HTTP-level test of login/refresh/change-password at all.

##### Token validation (HTTP)
- Negative: missing header, non-bearer scheme, garbage, tampered payload, wrong secret,
  `alg: none`, expired, missing `sub`/`org_id`, non-UUID `sub`, unknown user, user not a
  member of the token's org (403), deactivated mid-session.
- Existing: unit typing tests only. Gap: everything at HTTP level.

##### Every non-public route needs auth (route walk, unit, no DB)
- Every served HTTP route outside an explicit public allowlist answers 401 to no token and to
  a forged token; the allowlist is pinned exactly so a new public route fails the test.
- Existing: `tests/api/test_workspace_gate.py` checks the engineering gate per module, not
  authentication; `test_avatar_read_is_public_writes_are_not` covers avatars only.

##### RBAC (HTTP, real Postgres)
- Owner bypass: owner passes a permission no role grants; custom role based on `org_owner`
  is not the owner.
- Non-owner without the permission -> 403; custom role grants exactly its permissions; `any`
  vs `all` mode.
- Role edit / role assignment / role removal take effect on the next request.
- Grant ceiling over HTTP; system roles immutable; another org's custom role is 404.
- Deleting a custom role still held by members.
- Existing: unit `test_permission_set.py`, `test_role_grants.py`, `test_role_grant_matrix.py`,
  `test_role_validation.py`, mocked `api/v1/test_roles_base_role_validation.py`,
  `integration/test_people_security.py` (role ceiling cases).

##### Tenant isolation matrix (HTTP, real Postgres)
- Two orgs, each with an owner and rows: BUD, bug, bug comment, feature, tracked repo,
  design system, team, notification, office, custom role, member, employee profile, leave
  request, quiz review question. Org A's owner (passes every permission) tries to read,
  update and delete each of org B's rows by id -> 404/403 and B's rows unchanged in the DB;
  B's rows never appear in A's list responses.
- Existing: `integration/test_people_security.py` (organizations GET only),
  `test_employee_login.py` (one 404 case). Gap: almost all resources.

#### Findings

- Bug (fixed, `fix/role-delete-in-use`): deleting a custom role a member still holds hit the
  `org_to_user.role_id` FK and returned 500. Now 409 with the holder count.
- Bug (fixed, `fix/cross-org-references`): bug/BUD/TODO assignee accepted any user id, and
  `POST /bugs` accepted another org's `budId`/`featureId`; the response echoed the other
  org's member name / BUD title. Now 404.
- Open: `POST /members` with an email that exists in another org -> 500 (global unique
  email); reveals that the email exists on the instance. 409 vs "add existing user" is a
  product call.
- Open: login email match is case-sensitive (`User@x` != `user@x`).
- Open: `JWTToken` model is unused: no logout/revocation, and changing a password does not
  end other sessions. `change-password` does not ask for the current password.
- Open: no login rate limit or lockout.
- Open: `PATCH /members/{id}/status` and `set-password` act on the global user row; if one
  user ever belongs to two orgs, an admin of one org affects (or can sign in to) the other.
  Product flows can't create such a user today (global unique email).
- By design: `/api/v1/jobs/{id}` status/cancel don't check the org; the job UUID is the
  capability (same rule as the `job:` websocket topic).
- By design: `GET /buds/{other org bud}/timeline` answers 200 `[]` rather than 404 (no data).

#### Coverage matrix (what was added)

| feature | positive | negative | corner | existing test files | new test files |
|---|---|---|---|---|---|
| login / refresh / change-password | tokens work, refresh pair works, change then login | 5 wrong sign-ins identical 401; refresh with access/garbage token, lost member, deactivated | forced change blocks 3 routes, 7-char password 422, unicode password | core/test_auth_hardening.py, test_security_bcrypt_limit.py, integration/test_employee_login.py | integration/test_auth_login_flow.py |
| token validation | legacy untyped token, lowercase bearer | tampered payload, wrong key, alg none, expired, refresh-as-access, no sub/org, non-uuid sub, unknown user, garbage, Basic, no scheme | other-org token 403, deactivation and removal end live session | core/test_auth_hardening.py | integration/test_auth_token_validation.py |
| auth on every route | public list pinned exactly | ~340 routes x (no token, forged, refresh) -> 401 | MCP/bridge routes pinned to own checker | api/test_workspace_gate.py | api/test_route_auth_required.py |
| owner bypass / require_permissions | owner passes unheld permission, any-mode | admin/sales 403 | custom role based on org_owner gets nothing | core/test_permission_set.py | integration/test_rbac_owner_and_custom_roles.py |
| custom roles / role changes | custom role exact grants, edit widens/narrows next request, HR assignment | own role edit/assign 403, admin can't mint owner or touch owner | unassigned member = developer, system roles immutable | services/test_role_grants.py, test_role_grant_matrix.py, api/v1/test_roles_base_role_validation.py, integration/test_people_security.py | integration/test_rbac_owner_and_custom_roles.py, integration/test_rbac_role_changes.py |
| role delete in use | delete after reassign 204 | held role 409 (was 500) | - | - | integration/test_role_delete_in_use.py (fix branch) |
| tenant isolation (engineering) | control: own org reads 200, own rows listed | 25 cross-org probes on BUD/bug/comment/feature/design system/repo/team/quiz -> 404, rows unchanged column for column | timeline of foreign BUD is empty | - | integration/test_tenant_isolation_engineering.py |
| tenant isolation (people) | control reads 200, own rows listed | 23 probes on roles/members/merge/notifications/offices/employees/leave/org -> 404, rows + member unchanged | colleague's notification hidden from owner | integration/test_people_security.py | integration/test_tenant_isolation_people.py |
| foreign references | own links work | team member/repo, bug bud/feature, member role, managers -> refused | foreign feature link silently dropped | - | integration/test_tenant_isolation_references.py; integration/test_cross_org_references.py (fix branch) |

### Setup wizard, repositories, settings, Jira and design systems

Branch: `test/setup-settings`. Status: draft, matrix updated at the end.

#### Setup wizard
- init-org (`api/v1/setup.py`, `services/setup_init.py`)
  - Positive: org + admin + owner membership, JWT, one-time MCP token (hash at rest), Claude key or OAuth token encrypted at rest.
  - Negative: any unauthenticated setup endpoint (init-org, initialize, check-claude GET/POST, check-ai) is 403 once an org exists and creates nothing; duplicate slug is a 409 with no partial rows; bad slug / short password / bad email are 422; api_key mode without a key is 400.
  - Corner: second call (idempotency), host mode stores no secret, whitespace-only key.
  - Existing: `test_setup_two_stage.py` (fakes only). Gap: real DB rows, encryption at rest, the setup-complete gate.
- finalize-with-repos (`setup_finalize*.py`)
  - Existing: `test_setup_finalize_paths.py` (401/403, outside root, traversal, symlink, clone-root case variants, own clone). Gap: end-to-end on Postgres with a real local checkout and the init-org JWT.
- Local picker / add-by-path / branch lookup (`settings_repos_local.py`, `settings_repos.py`, `directory_listing.py`)
  - Existing: `test_settings_repos_local.py`, `test_settings_repos_add.py` (401/403, outside, `..`, symlink escape, clone root, happy paths).
  - Gaps: `~` expansion, sibling directory sharing the root's prefix, symlink that stays inside the root, unicode names, hidden dirs, monorepo flag, non-existent (404 / 400), file instead of dir, unreadable dir (403), relative path, very long names, NUL bytes, default (empty) path.
- Clone (`repo_cloner.py`): no direct tests today.
  - Positive: real clone from a local bare repo (git URL rewritten in the subprocess wrapper), default branch, re-clone updates and re-points origin.
  - Negative: non-GitHub hosts, lookalike hosts, bad characters, PAT scrubbed from errors, failed clone removes only what it created.
  - Corner: `.`/`..` segments in owner/repo/slug, purge helpers.
- Branch detection (`git_operations.py`): `test_git_branch_detection.py` covers worktree markers. Gap: multiple remotes, `HEAD ->` line, empty repo.
- `core/paths.py`: `test_paths.py` covers safe_join basics. Gap: absolute `relative`, unicode, NUL, `sanitize_filename`.

#### Settings and integrations
- Connections (`settings.py`): secrets encrypted at rest, masked on read, masked echo does not overwrite, permission (developer 403 on PATCH).
- Claude settings (`settings_claude.py`): key never returned, encrypted at rest, switching mode requires a credential, host clears it, developer 403.
- MCP tokens (`settings_mcp_tokens.py`): list only own org, revoke another org's token is 404 and keeps it.
- Organizations (`organizations.py`): other org's id is 404; non-owner cannot create.
- Tracked repos tenancy: org B cannot change, classify or remove org A's repo; same path in two orgs is two rows.

#### Jira import
- Connect stores the token encrypted and never returns it; disconnect removes it; sessions and review items of another org are 404; dedup thresholds (boundaries) and dedup is org-scoped.

#### Design systems
- Wrong-org get/put/delete/set-default are 404 and change nothing; developer (settings:view) cannot extract or edit.

#### Bugs found (each fixed on its own branch from origin/main)
- `fix/branch-detection-exact-match`: main/develop detection matched remote branch text by substring (`origin/devops` -> dev, `origin/main-legacy` -> main).
- `fix/clone-dot-segments`: cloner segment check accepted `.`/`..`; purging a repo named `..` deletes every org's clones.
- `fix/picker-unreadable-folder`: one unreadable child folder made the whole picker listing 403.
- `fix/repo-path-bad-input`: NUL byte or over-long name gave 500 in picker, branch lookup, add-by-path, finalize.
- `fix/finalize-duplicate-repo-ids`: two finalize entries for one checkout queued the repo id twice (parallel scans of one checkout).

#### Coverage matrix
| feature | positive | negative | corner | existing test files | new test files |
| --- | --- | --- | --- | --- | --- |
| init-org | owner role, JWT, MCP hash, key/token ciphertext | gate 403 after setup (5 unauth endpoints), 409 repeat slug, 400 bad AI choice, 422 bad slug/email/password | host stores nothing, clone purge scoped to slug | test_setup_two_stage.py | test_setup_complete_gate.py, integration/test_setup_init_org.py |
| finalize (local) | rows + branches, rerun updates, two orgs same path | developer 403; outside/missing/plain skipped | nothing usable starts no scan | test_setup_finalize_paths.py | integration/test_setup_finalize_local.py (+ duplicate test on fix branch) |
| picker / branch lookup | listing, sort, unicode, monorepo flag, symlink inside, `~`, default home | missing 404, file 400, unreadable 403, prefix sibling, relative path, `~` outside | master-only checkout | test_settings_repos_local.py | test_settings_repos_local_edges.py (+ fix branches) |
| add-by-path | detect branches, re-add reactivates, unicode | developer 403, missing/file 400 | `..` spelling collapses to one row | test_settings_repos_add.py | integration/test_settings_repos_register.py |
| clone | real clone from local bare repo, update path, SSH/HTTPS forms, per-org folders | non-GitHub/lookalike hosts, bad chars, failed clone 400 with no row | PAT scrubbed (literal + quoted), half-written clone removed, foreign folder kept, purge scoping | test_settings_repos_clone.py, test_job_repo_bulk_clone.py | test_repo_cloner.py, test_repo_cloner_failures.py (+ fix branch) |
| path predicates | in_clone_root, safe_join unicode/symlink | prefix siblings, climbing out | case-folded root, long paths | test_paths.py | test_clone_root_guard.py |
| connections secrets | Slack token/secret and GitHub key as ciphertext, masked read | developer 403, bad signing secret 400 (rolls back token), workspace taken 409 | masked echo keeps real values | test_settings_connections_status.py | integration/test_settings_slack_secrets.py, test_settings_ai_secrets.py |
| Claude settings | key ciphertext, never returned | developer 403; blank key, bad mode, bad provider 400 | switching mode needs new credential, host clears | - | integration/test_settings_ai_secrets.py |
| tenancy (repos, org, MCP tokens) | owner reaches own repo | other org 404 on 6 repo routes, org read, token revoke | developer cannot list tokens | test_mcp_token_integrity.py | integration/test_settings_repos_tenancy.py |
| design systems | set-default within one org, customisation round trip | other org 404 on 5 routes, developer 403 on 4 writes, extract for other org's repo 404 | blank customisation clears | - | integration/test_design_system_access.py |
| Jira | connect stores ciphertext, disconnect | rejected token stores nothing, developer 403, other org's sessions/review items 404 | review action state rules | test_jira_adf_converter.py, test_jira_field_mapper.py | integration/test_jira_connection_access.py |
| Jira dedup | nearest wins | other org's identical BUD never matches | thresholds half-open at 0.25/0.40, no embeddings, exclusions | - | test_jira_dedup.py, integration/test_jira_dedup_scope.py |

### BUD lifecycle

Branch `test/bud-lifecycle`. Scope: BUD create / numbering, status transitions and gates,
terminal states (closed, discarded/restore), `on_bud_closed`, edit history and revert
(#389), linked features, testing tab gate, closure rewards. MCP handlers, agent result
handlers and leave are out of scope.

Known flaky, not touched: `tests/integration/test_bud_design_upsert_concurrency.py`.

#### Map of the area

- `api/v1/bud.py` `create_bud`: `next_bud_number()` = `max+1` per org (no lock; unique
  `(org_id, bud_number)`), inline embedding (failure swallowed), planned feature
  `BUD-NNN`, `created` timeline event, auto-assign.
- `api/v1/bud.py` `update_bud` (PATCH): order is QA scope (403) -> terminal guard
  (closed/discarded -> 400) -> design-generating guard (409) -> section edit policy (409)
  -> `transition_feature_for_bud` -> code_review->testing reason gate (400) ->
  testing->uat/prod pending manual-case gate (400) + `qa_skip` override event ->
  status_change event -> version snapshot -> assignee XP 50 (`bud:N`) only when leaving a
  non-prod/closed status -> `on_bud_closed` for prod and closed. The handler does not lock
  the BUD row.
- `services/bud_closure.py` `on_bud_closed`: contributor XP 25 (`bud_contrib:N:uid`,
  assignee excluded), metrics + Learning Agent only on CLOSED (metrics in a savepoint),
  developer SP, QA/PM/designer/tech-arch SP on CLOSED. No scan.
- `api/v1/bud_workflows.py` restore (row lock, 409 unless discarded), `services/bud_restore.py`.
- `api/v1/bud_versions.py` + `services/bud_version_restore.py` + `repositories/bud_version.py`
  (cap 20 per phase, reverts excluded), chat edits in `services/chat_persistence.py`
  snapshot under the section's owning phase (#389).
- `api/v1/bud_qa.py` manual results (row lock), evidence; `api/v1/bud_linked_features.py`
  + `repositories/bud_feature_link.py` (org-scoped).
- #388 has no backend code change (only the tech-planner skill text); nothing to cover.

#### Features, cases, existing tests, gaps

1. Create + numbering. Pos: first BUD is 1, then 2; numbering per org. Neg: empty title
   422, viewer 403. Corner: embedding failure still creates; concurrent creates.
   Existing: none at API level. Gap: all.
2. Terminal states. Pos: discard then restore via API lands in previous phase. Neg:
   status change on closed 400, second close 400, status change on discarded 400,
   restore of closed/active 409, QA restore 403, other org 404. Corner: title edit on
   closed. Existing: `test_bud_restore_roundtrip.py` (service), `test_bud_restore_endpoint.py`
   (mocked). Gap: real API terminal guards.
3. Testing gate. Pos: all cases terminal -> uat; skipped -> `qa_skip` override; closing
   from testing with pending allowed. Neg: pending -> 400 (uat and prod), no side effects
   left. QA scope: testing->uat allowed, other transitions/fields 403. Corner: >5 pending
   ids truncated. Existing: `test_bud_qa_status_revert.py`, `test_qa_role_permissions.py`
   (mocked). Gap: real API.
4. code_review->testing reason gate. Neg: missing/blank reason 400. Pos: reason recorded
   trimmed. Existing: none. Gap: all.
5. Close side effects. Pos: assignee XP 50 once, contributors 25, no scan rows. Corner:
   prod then closed awards once, discard+restore+close awards once. Existing:
   `test_sp_lifecycle.py` (SP only). Gap: XP + no-scan + exactly-once.
6. `on_bud_closed` direct. Pos/neg/corner: contributor XP excludes assignee and dedups,
   metrics/agent only on CLOSED, agent only when opted in, agent failure and metrics
   failure do not block XP. Existing: none. Gap: all.
7. History/revert (#389). Pos: PATCH snapshot, revert restores, chat edit snapshot under
   owning phase and revertible. Neg: rejected PATCH leaves no version, revert after
   phase moved 409, revert closed 400, other org 404. Corner: unchanged chat content no
   row, cap of 20 with reverts excluded. Existing: unit tests with mocks
   (`test_chat_persistence.py`, `test_bud_version_restore.py`, `test_write_bud_history.py`).
   Gap: real DB round trip.
8. Linked features. Pos: link/list/unlink. Neg: other-org feature dropped, other-org BUD
   404, unlink missing 404, viewer 403. Corner: duplicate ids. Existing: none at API.

#### Coverage matrix

(updated at the end with what was added)

| feature | positive | negative | corner | existing test files | new test files |
| --- | --- | --- | --- | --- | --- |
| Create + numbering | 1, 2 per org; max+1 after gaps; embedding, planned feature, `created` event | 422 bad payloads; 403 viewer/dev/qa/role-less | embedder failure; unicode title; concurrent creates (fix branch) | none at API level | test_bud_create.py; fix: test_bud_number_concurrency.py |
| Closed / discarded terminal | discard -> restore lands in old phase; closed title still editable | status change on closed 400 (incl. second close); discarded 400; restore closed/live 409; QA restore 403; other org 404; unknown status 400 | closed requirements 409; second restore 409; concurrent close (fix branch) | test_bud_restore_roundtrip.py, test_bud_restore_endpoint.py | test_bud_terminal_states.py; fix: test_bud_patch_concurrency.py |
| Testing gate (manual cases) | all terminal -> uat; qa_skip override with skipped ids; clean exit no override; close from testing with pending | pending -> uat/prod 400, no event, no bg estimate | >5 pending truncated | test_bud_qa_status_revert.py (mocked) | test_bud_testing_gate.py |
| QA tab + QA role | QA marks results then promotes; summary counts | QA other transitions / fields 403; manual results other org 404, unknown case 404 | revert to pending clears attribution, re-arms gate | test_qa_role_permissions.py | test_bud_qa_tab.py |
| code_review -> testing | all merged: no reason | open / closed / no PR with no or blank reason 400 | reason trimmed; no impacted repos | none | test_bud_code_review_gate.py |
| Close side effects (PATCH) | assignee 50 XP once; contributors 25 once; Learning Agent iff opted in, only at closed | second close 400 adds nothing | prod then closed pays once; no assignee; XP total == events; no scan rows / entry points; feature untouched | test_sp_lifecycle.py (SP) | test_bud_close_side_effects.py |
| `on_bud_closed` direct | commit + PR contributors paid once over 3 firings | assignee never a contributor | prod firing skips metrics + agent; metrics crash rolls back alone; agent crash swallowed; no contributors | none | test_bud_closure_hook.py |
| Auto-close (release) | prod / uat close once, pay once | partial release, testing, discarded, no repos untouched | repeat delivery no-op; from-status (fix branch) | none | test_bud_auto_close.py; fix: test_auto_close_from_status.py |
| XP dedup | - | duplicate source_ref loses race | total / level unchanged (fix branch) | test_member_merge_xp_sp.py | fix: test_xp_dedup_race.py |
| History / revert (#389) | PATCH snapshot; revert restores, logs revert row + event; chat edit snapshot revertible | rejected PATCH no row; revert after phase moved 409; closed 400; unknown version 404; other org 404; QA revert 403 | unchanged chat no row; chat filed under owning phase; chat on foreign BUD no-op; cap 20 with reverts excluded | test_chat_persistence.py, test_bud_version_restore.py, test_write_bud_history.py (mocked) | test_bud_history_revert.py, test_bud_history_chat_edits.py |
| Linked features | link / list / unlink, timeline events | foreign + inactive features dropped; other-org BUD 404; viewer 403; empty body 422 | duplicate ids, relink, unlink twice 404 | none at API | test_bud_linked_features_api.py |
| Bug gate | threshold reached -> development, QA freed, events | settled bugs do not count | only acts in testing (closed untouched) | none | test_bud_bug_gate_and_review_sp.py |
| Review SP / shipped SP | valid reviewer paid once; completed todos by substance | rubber stamp, self review, PM, unknown login, blank comment unpaid | unjudged weight 1; assigned fallback; contributors last; empty BUD | test_sp_lifecycle.py | test_bud_bug_gate_and_review_sp.py, test_bud_shipped_sp_recipients.py |
| Estimate overrides | override visible in estimates / history / timeline; deadline rules | disabled / non-pipeline phase 400; empty reason 422; viewer 403; other org 404 | other phase leaves current deadline | test_estimation_*.py (engine only) | test_bud_estimate_overrides.py |

Not covered: todos API (`bud_todos.py`), designs routes beyond existing upload tests, tech-arch approve/reject workflows, code review status/override/regenerate routes, evidence upload/download (existing unit tests only), estimation engine numbers (existing unit tests).

#### Review round 2 additions
- Fail-closed guard `app_database_blocked` (autouse via import) + self-test `test_bud_lifecycle_guard.py`.
- `test_bud_development_start.py` (todo sync, lead assignment, deferred estimate, no duplicates on re-entry).
- `test_bud_code_review_override.py`; two-repo cases in `test_bud_code_review_gate.py`.
- Fix branch `fix/auto-close-learnings` (auto-close never wrote learning metrics).
- `fix/bud-patch-row-lock` now uses FOR NO KEY UPDATE and also locks in history numbering (all writers).
- Not pinned (open questions): feature status after close; pay-outs when closing from testing.
- DELETE /buds/{id}: 500 when a bug or a FeatureLearning row references the BUD (FKs without ondelete); open question, needs a migration.

### Agents, jobs and the MCP server

Branch `test/agents-mcp`. Claude/Codex/Copilot/Ollama never run: every handler under test
is reached through HTTP or called directly; embeddings, Slack and redis are stubbed.

#### MCP server (`app/mcp/`)

29 tools in `server.MCP_TOOLS`. Dispatch: `TOOL_HANDLERS` (org only, 19 tools) and
`AUTH_TOOL_HANDLERS` (org + user, 10 tools). `/mcp/tools/{name}` exposes all 29 to any valid
token; `/mcp/sse` (streamable) only the 10 in `REMOTE_TOOLS`.

Cross-cutting, applied in `call_tool` before any handler runs:
- auth `verify_mcp_token`: internal in-memory token -> per-user token (expiry, inactive user,
  non-member, engineering permission) -> org token -> 401.
- `enforce_rate_limit` (redis fixed-window, per (principal, ip) 60/min and per principal
  300/min, fail open).
- `emit_audit` on every exit (200, 404 unknown tool, handler HTTPException, 500, 429) via
  a fresh `AsyncSessionLocal` session; params pass an allowlist and a 500-char cap.

Existing tests: `tests/mcp/*` (mocked session; audit call capture; remote allowlist; token
inactive/non-member/permission with mocked repos; code_graph_repo errors with mocks;
bud writes with mocks). No real-DB MCP test, no rate-limit test, no audit-row test.

##### Coverage table: tool x (auth, org scope, validation, audit)

Auth and audit are enforced once in `call_tool`, so they are covered per route with a
representative tool, plus per-user-token requirement checks for the AUTH tools.

| tool | auth | org scope | validation | audit |
|---|---|---|---|---|
| get_bud_context | route matrix (new) | B's BUDs not listed (new) | limit type (bug, see below) | success row (new) |
| create_bud | org token refused (new) | links to B's feature dropped (new) | missing title, long title (bug) | via route |
| update_bud | org token refused (existing mock + new) | B's bud_id -> not_found (new) | bad uuid, nothing_to_update (new) | via route |
| get_bud_by_id | via route | B's id/number -> not_found (new) | missing id, bad uuid, bad number (new) | via route |
| write_bud | via route | B's number -> not found, B untouched (new) | missing body (existing) | via route |
| get_features | via route | B's features hidden (new) | - | via route |
| get_pending_features / write_feature_registry / write_synthesis_feature / check_feature_exists | via route | scan guard (existing) | - | via route |
| search_bugs | via route | B's bugs hidden (new) | - | via route |
| post_slack_message | via route | org bot token only | no token configured (new) | via route |
| get_team_context | via route | B's people hidden (new) | - | via route |
| list_design_systems / get_design_system | via route | B's repo id -> not found (new) | bad repo_id uuid (bug) | via route |
| get_prompt | via route | existing | existing | via route |
| get_bud_designs | via route | B's bud -> empty (new) | bad uuid (new) | via route |
| write_bud_design | via route | B's bud_id accepted (bug) | bad uuid (new) | via route |
| get_bud_plan / takeover_todo / complete_todo / create_todo / update_todo | org token refused (new) | B's bud_number -> not found (new) | missing params (new); non-int (bug) | via route |
| code_impact / code_query / code_context / code_community / code_god_nodes / code_stats | via route | B's repo id -> not tracked, only A's repos listed (new) | name instead of uuid (existing mock + new real DB) | params kept (existing) |

Route-level auth matrix (new, real Postgres): no header (422), non-Bearer, unknown token,
expired token, deleted (revoked) token, inactive user, member removed from org, role
without engineering access (403), valid per-user token, org-level token, internal token.

#### Jobs

`job_queue.py` (in-memory store, worker loop, cancel), `api/v1/jobs.py` (status + cancel).
Existing: `test_job_queue_find_active.py`, `test_job_handlers.py`, bud chat API tests.
Gaps: worker success / failure / cancel paths, duplicate and blank job ids, shutdown
refusal, TTL cleanup, cancel of queued vs terminal jobs, unknown job id 404, and a job
from another org (status and cancel).

#### Agent output

`agent_markdown.py`, `json_parser.py`, `design_output_fallback.py`, `tech_planner_patch.py`
already have unit tests. `agent_task_cancel.py` has none: cancel of an orphan task and of
per-repo designs with roll-up into the parent task (real Postgres).

#### Coverage matrix

| feature | positive | negative | corner | existing test files | new test files |
|---|---|---|---|---|---|
| MCP token auth (route) | user, org, internal token | no header, malformed, unknown, expired, revoked, inactive, removed member, hr role (403) | future expiry, last_used_at stamped | tests/mcp/test_inactive_user_revocation.py | integration/test_mcp_token_auth.py |
| MCP org scope: BUD tools | own BUD read/write | B's uuid, number, todos, feature links | same BUD number in both orgs | tests/mcp/test_bud_writes.py | integration/test_mcp_org_scope_buds.py |
| MCP org scope: repo tools | own repo / design system | B's repo on 6 code tools, design systems, designs, team | repo name instead of uuid, unscanned repo | tests/mcp/test_code_graph_repo_errors.py | integration/test_mcp_org_scope_repos.py |
| write_bud_design scope | own bud + repo | B's bud, B's repo | with and without repo_id | - | fix branch: integration/test_mcp_design_write_scope.py |
| MCP audit rows | success row with ids, ip, UA, safe params | unknown tool 404, soft error, failed auth (no row) | 5000-char param capped, internal token | tests/mcp/test_audit_log_*.py | integration/test_mcp_audit_rows.py; fix branches: test_mcp_audit_long_fields.py, test_mcp_audit_after_db_error.py |
| MCP rate limit | under cap | per-client 429, global 429 | tool weights, TTL once, XFF keying, redis down / erroring | tests/mcp/test_remote_allowlist.py (costs) | mcp/test_rate_limit.py |
| TODO tools | plan, claim, complete, create, edit | second claim, non-holder complete, closed BUD, missing params | simultaneous claims, double complete, 2000-char description | - | integration/test_mcp_todo_flow.py |
| job queue | complete, notify owner | crash -> FAILED, unknown type, blank / reused id, shutdown | cancel running, parallel workers, backpressure, TTL cleanup | tests/services/test_job_queue_find_active.py | services/test_job_queue_store.py, test_job_queue_workers.py; fix branch: test_job_queue_cancel_queued.py |
| jobs API | status, cancel queued | unknown id 404 | repeat cancel / terminal no-op | - | api/v1/test_jobs_endpoints.py |
| agent task cancel | orphan, live signal | signal failure, wrong org | race with normal finish | - | integration/test_agent_task_cancel.py |
| design cancel roll-up | complete when one ready | fail when none ready | other repo still generating, already-ready design | - | integration/test_agent_design_cancel.py |
| #388 skill rule | rule present | old rule absent | examples parse | - | services/test_tech_planner_mermaid_rule.py |

### Repo scanning, features, bugs and triage

Branch `test/scan-features-bugs` (cut from origin/main @ c4303ebd).

#### Map of the area

| Feature | Code | Existing tests |
| --- | --- | --- |
| GitHub webhook (repo-scoped PR events) | `api/v1/github_webhook.py` | `tests/api/v1/test_github_webhook_payload.py` (pure `_build_pr_merge_replay_payload`), `tests/api/v1/test_github_install_webhook.py` (install events, fakes only) |
| PR-merge worker / dispatcher | `services/pr_merge_worker.py`, `services/scan/pr_merge_update.py` | `test_pr_merge_worker.py`, `test_pr_merge_update_cap.py`, `tests/repositories/test_webhook_log_replay.py` |
| Release detection (fast path vs SHA walk) | `services/github_webhook_handler.py::_maybe_detect_release_promotion`, `services/release_detection.py` | `test_resolve_release_stage.py` (branch mapping only) |
| Feature lifecycle | `services/feature_lifecycle.py` | `tests/integration/test_bud_restore_roundtrip.py` (discard/restore only) |
| Feature reconciler | `services/feature_reconciler.py` | six `test_feature_reconciler_*` files |
| SHA-keyed caches + skip predicates | `repositories/cluster_cache.py`, `repositories/repo_graph_cache.py`, `services/scan/stages/_skip_predicates.py` | `tests/scan/test_cluster_index.py` (mocked), `test_synthesize_skip.py` |
| Features API | `api/v1/features.py`, `repositories/feature_reads.py` | `tests/repositories/test_feature_reads_in_progress_filter.py`, `test_people_security.py` (sales role 403) |
| Bugs API | `api/v1/bugs.py`, `_bug_serializers.py` | none |
| Bug comments | `api/v1/bug_comments.py` | none |
| Bug attachments | `api/v1/bug_attachments.py`, upload policy | `tests/api/v1/test_bug_attachments.py`, `test_upload_policy.py` (good coverage) |
| Bug linker | `services/bug_linker.py` | none (`test_bug_threshold.py` is the QA bug-count threshold, not the linker) |
| Slack signature | `services/slack_verify.py` | none |
| Slack intake / QA router / triage priority | `slack_intake.py`, `slack_qa_router.py`, `triage_priority.py` | `test_slack_intake_*`, `test_slack_qa_router.py`, `test_slack_qa_intent_dispatch.py`, `test_triage_priority_normalize.py` |
| Triage sessions API | `api/v1/triage_sessions.py` | none |

#### Per feature: cases

##### GitHub webhook, repo-scoped events
- Positive: merged PR into `main_branch` → 200, `webhook_logs` replay row `pending` with replay payload, publish to stream called once, handler called once.
- Negative: missing signature / event header → 400; missing delivery id → 400; invalid JSON → 400; bad signature → 401 and no log row, no handler; signed with another org's secret → 401; untracked repo → 200 no-op; org without secret → 200 no-op.
- Corner: duplicate delivery id → `{"status":"duplicate"}`, handler not re-run; merge into `develop` → audit row `skipped`, no publish; repo with no `main_branch` → skipped; publish failure is non-fatal (200, row stays pending).

##### Release detection
- Fast path (PR has bud_id): `merged_to_prod` timeline event with release PR detail; no GitHub call.
- SHA walk (no bud_id): commits mapped through `merge_commit_sha` and `dev_activity_logs.commit_sha` → one event per BUD; GitHub client mocked.
- Negative: base branch not a stage → nothing; another org's PR with the same SHA must not match.
- Corner: webhook redelivery idempotent (one event); auto-close only when every impacted repo shipped; BUD in testing never auto-closes; UAT stage gated by org toggle.

##### Bug linker (0.40 BUD / 0.35 feature cosine distance)
- Real pgvector, hand-crafted 384-d integer vectors so distances are exact: exactly-at (link), just-below (link), just-above (no link) for both pools.
- Negative: embedding failure → no link, no embedding; other org's BUD/feature at distance 0 never links; inactive feature never links; manual `bud_id` never overwritten; production bug never falls back to a BUD.

##### Bugs API
- Positive: create (linker mocked), list/board/get, PATCH status stamps `resolved_at`/`rejected_at` once.
- Negative: other org's bug → 404 on get/patch; viewer cannot create (403); developer cannot reassign (403, `bugs:assign`); PATCH to another org's BUD/feature → 404; create with another org's BUD id; bad severity → 422.
- Corner: bug numbers are per org; board defaults to production bugs.

##### Bug comments
- Positive: post, list oldest-first, author edits, author deletes (tombstone, body hidden).
- Negative: another org's bug → 404; comment id from another bug → 404; non-author without edit → 403; viewer cannot post → 403; empty / 10001-char body → 422; editing a deleted comment → 409.
- Corner: delete is idempotent; moderator (`bugs:edit`) may edit others; unicode round trip.

##### Features API
- Positive: list, mode filters (active / deactivated), `q` search, by-repo grouping, get one.
- Negative: other org's feature → 404 on get and absent from lists; bad `mode` → 422; bad `matchVia` → 422.

##### SHA-keyed caches and skip predicates
- `should_skip_indexing`: hit on same SHA, miss on new SHA, miss for another org's scope, `force_reindex`, empty SHA.
- `replace_for_repo_sha` prunes clusters gone at the same SHA and leaves other SHAs alone; replacing with `[]` empties the SHA.
- `repo_graph_cache` round trip, last write wins, other SHA / org → None.

##### Feature lifecycle
- `create_planned_feature`: planned row, `bud:` signature, no PRIMARY junction, upsert on re-create (same id), revives an inactive row; embed failure keeps the row.
- `transition_feature_for_bud`: development → in_progress; design keeps planned; in_progress not regressed; other org's same BUD number untouched.
- `extract_feature_from_bud` pure parsing: prefix stripping, first paragraph, capabilities capped at six, stop words, empty input.

##### Slack signature
- Valid; exactly 300 s old accepted; 301 s rejected; future skew rejected; non-numeric timestamp; tampered body; wrong secret; reason never leaks secret.
- `verified_org`: missing fields, unknown team, undecryptable secret, wrong org's secret → None.

#### Coverage matrix

(filled in at the end, see below)

#### Coverage matrix (final, what was actually added)

All new integration files are under `backend/tests/integration/`; unit files under `backend/tests/services/`.

| feature | positive | negative | corner | existing test files | new test files |
| --- | --- | --- | --- | --- | --- |
| GitHub webhook, repo PR events | merge into main queued (replay row, payload, publish, setup PR flip) | bad sig x4 (wrong secret, tampered body, no prefix, other org's secret) → 401 and nothing recorded; missing headers → 400; bad JSON → 400; untracked repo; org without secret | redelivery → duplicate, handler once; develop / release / no main_branch → skipped audit row; publish failure → 200, row stays pending | test_github_webhook_payload.py, test_github_install_webhook.py | test_github_webhook_pr_events.py (+ github_webhook_support.py) |
| Release detection | fast path merged_to_prod + auto-close; SHA walk via merge_commit_sha and dev commits | other org's matching SHAs never match; non-stage base; UAT toggle off | redelivery idempotent (one event); partial impacted repos do not close; testing/closed BUDs never auto-close; GitHub failure keeps PR bookkeeping | test_resolve_release_stage.py | test_release_detection.py (+ release_detection_support.py) |
| Bug linker 0.40 / 0.35 | exactly at, just below link (BUD and feature pools) | just above no link; other org identical vector; deactivated feature; production bug never falls back to BUD; testing bug ignores features | manual bud_id kept; BUDs without embeddings; closest of several; embedding failure → no link, no embedding | none | test_bug_linker_threshold.py, test_bug_linker_scoping.py (+ bug_linker_support.py) |
| Bugs API | auto-link on create, feature → production + background embed, UAT BUD → production, numbering per org, status stamps, board default, list filter/paging | other org 404 (get/patch/list/board); cross-org link on PATCH 404; non-engineering role 403; viewer read-only; reassign needs bugs:assign; invalid bodies 422; bad status 422 | unassigned member = developer perms; resolvedAt kept on later moves; pageSize > 100 → 422 | test_bug_attachments.py, test_sp_event_emission.py | test_bugs_api_access.py, test_bugs_api_lifecycle.py |
| Bug comments | post, list oldest first, edit, delete tombstone, comment count | other org 404 x4; comment via another bug 404; non-author 403; viewer cannot post; empty / 10001 chars 422 | idempotent delete; edit after delete 409; moderator override; unicode; exactly 10000 chars | none | test_bug_comments_api.py |
| Features API | view modes with matching totals, search, paging, by-repo grouping, retired single feature | other org invisible (get/list/by-repo/repoId filter); unknown id 404; bad params 422; bad matchVia 422; non-engineering 403 | blank search; planned rows excluded from by-repo | test_feature_reads_in_progress_filter.py | test_features_api.py |
| SHA-keyed caches / skip | unchanged SHA skips indexing with reason | new SHA, force_reindex, empty SHA; other org never short-circuits | replace prunes vanished clusters only for that SHA; empty replace re-enables indexing; biggest-first order; graph last-write-wins, unicode nodes | test_cluster_index.py (mocked) | test_scan_cache_short_circuit.py |
| Feature lifecycle | planned row (no junction, bud: signature, capabilities, embedding); development → in_progress | no feature → no-op; other org untouched | re-create upserts and revives same row; never regresses in_progress; embed failure still creates row | test_bud_restore_roundtrip.py (discard/restore) | test_feature_lifecycle_registry.py, test_feature_extract_from_bud.py |
| Triage approval queue | approve → one BUD, priority, embedding, planned feature, Slack post, agent task; reject | other org 404 + not listed; non-approver 403; unknown 404; bad status filter 400 | decided once (409 for every second decision); no bot token → no Slack | none | test_triage_sessions_api.py (+ triage_support.py) |
| Slack bug intake approval | PM approval files bug linked to closest BUD with context fields | developer, unknown Slack user, PM of another org refused | bare summary falls back; rejected / feature sessions ignored | test_slack_intake_*.py | test_slack_bug_intake_approval.py |
| Slack signature | valid; exactly 300 s accepted | 301 s, future skew, non-integer ts, tampered body, other secret, re-timestamped replay, malformed sigs; verified_org missing fields / unknown team / unusable secret / other workspace's secret | reason never leaks secret | none | test_slack_verify.py |

Regression tests for the product fixes live on their fix branches (see report).

### People and leave

Branch `test/leave`. Area: `app/services/leave/**`, `api/v1/leave*.py`, offices, holidays,
calendar sync, reports, Slack actions/status, leave repositories.

Existing coverage is broad (37 integration files, 19 unit files). New tests target what was
missing, with "today" frozen through `tests/integration/leave_edge_support.freeze_today`
(patches every module that imported `policies.today_for`), so real calendar dates (Dec 31,
Mar 31, Feb 29) are used instead of `date.today()`-relative ones.

#### Features

##### Request / approve / reject / cancel / edit
- Positive: submit, approve by any manager, HR fallback with no manager, cancel pending and
  approved-future leave, manager reschedule/withdraw. Existing: test_leave_flows,
  test_leave_routes, test_leave_changes(_under_way), test_approval_queue.
- Negative: own request (403), peer (403), other org (404), rejection without note (422).
  Existing covered plain-member outsiders only.
- Corner / gaps filled:
  - two approvals at once, two rejections at once (one note kept), approve racing the
    requester's cancel (always ends cancelled, days returned), re-deciding a rejected
    request either way, cancelling a rejected one -> `test_leave_decision_races.py`
  - HR of another org: 404 on approve/reject/cancel/reschedule/withdraw; a user who is HR in
    org B and a plain member of org A gets 403 in A and 404 from B; the only HR with no
    manager gets `no_approver`, a second HR can approve them but they still can't approve
    themselves; HR override then a late manager approval is 409 ->
    `test_leave_tenant_decisions.py`, `test_leave_reschedule_years.py`
  - manager moves leave from December into January: priced on the new year, freed days pay
    December's loss of pay; moves spanning both years / weekend only / before today change
    nothing -> `test_leave_reschedule_years.py`

##### Loss of pay, accrual, carry-forward, leave years (#387)
- Existing: test_loss_of_pay(_changes), test_leave_rebalance (#387), test_leave_accrual,
  test_leave_carry_forward, unit accrual/allocation/carry_rule/rules.
- Gaps filled:
  - balance moved across zero by HR over HTTP: exactly booked -> 0 left 0 LOP; -1 -> latest
    leave gets 1 LOP, earliest stays paid; +0.5 / +0.5 back; +1 -> 1 spare, never negative
    LOP; -10 -> all booked (approved and pending) LOP, days left 0 not negative; adjusting 0
    days is 422; a grant to another year leaves this year's LOP alone; rejecting earlier
    leave pays later LOP -> `test_leave_rebalance_bounds.py`
  - pure: `split_totals` (no entries, corrections either sign, added/removed kept apart,
    carry in/out, no-allocation corrections), `headroom_from` negative vs `usable_from`
    floored at 0, deductions only at year end, grants usable at once, `split_paid` at zero
    -> `tests/services/test_leave_balance_floor.py`
  - Dec 31 / Jan 2 drawing on different years, Dec 31-Jan 1 refused, last bookable day of
    next year; April leave year splitting at Mar 31 (message names the split day), monthly
    accrual restarting Jan 1, leap day counted and priced on February's accrual and excluded
    when a holiday -> `test_leave_year_boundaries.py`
  - pure leap/fiscal maths: leave-year bounds containing Feb 29 for start months 1-4,
    366-day daily proration, accrual on Feb 29 in an April year, `same_leave_year` at each
    boundary, backdate limit exactly at the edge -> `tests/services/test_leave_year_math.py`
  - carry-forward on an April policy (due Apr 1-7 only, once; carry-out keeps earlier leave
    paid, days left 3 old / 23 new), January and April policies in one org each carry on
    their own new year -> `test_leave_carry_fiscal_year.py`

##### Half days, holidays per office, weekends, WFH
- Existing: test_leave_calendar_edits (AM+PM), test_leave_period_limits, unit rules
  (half day on holiday), test_leave_flows (WFH allowance), test_offices (placement).
- Gaps filled:
  - same half / full day / wider range clash with a half day; the other half doesn't; two
    halves cost 1 day and cancelling one returns 0.5; last 0.5 of balance -> a full day is
    0.5 LOP; half-day WFH uses half the allowance, monthly reset, cross-month request goes to
    the manager whole -> `test_leave_half_days.py`
  - two offices placed through the employee API with their own policies: a holiday in one is
    a working day in the other (week, single day, half day), a Saturday worked only in one,
    optional holidays still count, each viewer's calendar shows their own office's holidays,
    a holiday added to one office recounts only its pending leave
    -> `test_leave_office_holidays.py`

##### Team calendar privacy
- Existing: test_calendar_hides_leave_type_from_peers (service level, peer vs manager).
- Gaps filled over HTTP: requester, direct manager and HR see type and reason; skip-level
  boss and peer don't; pending leave visible only to the requester; another org sees
  nothing; range 1..93 days (94 -> 422, end before start -> 422)
  -> `test_leave_calendar_visibility.py`

##### Reports
- Existing: test_leave_reports(_edges), unit report_export/report_scope.
- Gaps filled over HTTP: employee name, department, decider name and leave type name that
  start with = + - @ come out prefixed with `'` in register/summary/balances CSV, a negative
  adjustment stays a number; a range with no leave -> JSON [] and CSV header only; range one
  day to a year (365 ok, 366 422, leap year whole year ok)
  -> `test_leave_reports_csv_edges.py`

##### Slack approvals (mocked)
- Existing: test_leave_slack_actions (approve, forged/unsigned, wrong user, reject note,
  second click).
- Gaps filled: correctly signed but 10-minute-old click (401); another org's workspace
  naming this org's request id ("Request not found."); reject form from a non-approver;
  reject form after another manager approved ("M2 already approved..."); deactivated
  manager treated as unlinked; malformed/other action ids -> `test_leave_slack_edges.py`

##### Google Calendar sync (mocked)
- Existing: unit reconcile (`_apply`) and event shapes.
- Gaps filled: respx-level client: list asks only for our private tag on every page, all
  event types, 409 create -> PUT, delete 404/410 is done, errors carry Google's message
  -> `tests/services/test_leave_calendar_api.py`; end to end `sync_request` against the
  test DB and a fake Google holding a person's own event: approved WFH -> one entry per
  working day (holiday skipped), idempotent re-run, cancel removes only that request's
  entries, pending or other org's request opens no calendar
  -> `test_leave_calendar_sync_flow.py`

#### Coverage matrix (after this work)

| feature | positive | negative | corner | existing test files | new test files |
| --- | --- | --- | --- | --- | --- |
| submit/approve/reject/cancel | yes | yes | races, re-decide, approve vs cancel | test_leave_flows, test_leave_races, test_leave_routes | test_leave_decision_races |
| who decides (HR, cross-org) | yes | yes | dual-org member, sole HR | test_leave_flows, test_approval_queue, test_leave_routes | test_leave_tenant_decisions |
| manager edits / withdraw | yes | yes | across year end, other org | test_leave_changes(_under_way) | test_leave_reschedule_years |
| LOP / rebalance (#387) | yes | yes (0 days) | -1, +0.5, -10, other year, reject | test_loss_of_pay*, test_leave_rebalance | test_leave_rebalance_bounds, services/test_leave_balance_floor |
| leave years / accrual | yes | yes | Dec31/Jan1, April year, leap day | test_leave_accrual, services/test_leave_rules | test_leave_year_boundaries, services/test_leave_year_math |
| carry-forward | yes | yes | April year, two policies | test_leave_carry_forward | test_leave_carry_fiscal_year |
| half days / WFH | yes | yes | same half, last half day, month edge | test_leave_calendar_edits, test_leave_period_limits | test_leave_half_days |
| office holidays / week | yes | yes | half day on holiday, optional, recount | test_offices, test_leave_policy_moves | test_leave_office_holidays |
| team calendar | yes | yes | skip-level, pending, range bounds | test_leave_flows | test_leave_calendar_visibility |
| reports / CSV | yes | yes | formula text, empty range, range bounds | test_leave_reports(_edges), services/test_leave_report_export | test_leave_reports_csv_edges |
| Slack approvals | yes | yes | replay, other workspace, stale form | test_leave_slack_actions | test_leave_slack_edges |
| Google Calendar sync | yes | yes | paging, 409, foreign events | services/test_leave_calendar_reconcile, _events | services/test_leave_calendar_api, test_leave_calendar_sync_flow |

### Employee records and gamification

Branch `test/people-gamification` (from origin/main c4303ebd). Backend only.

#### Map

- Employee records: `api/v1/employees*.py`, `services/employees/*`, `core/hr_crypto.py`.
  Access rules are pure (`access.py`, `sensitive_access.py`); routes resolve the record
  in the caller's org via `_employee_helpers.load_record` (404 elsewhere).
- XP: `services/xp_service.award_xp` (dedup on `(source_ref, org_id)`, rounding, level-up,
  `xp:{user}` publish), `check_and_award_streak` (UTC day), `api/v1/xp.py` (me,
  leaderboard, history, unlock-vehicle, upgrade-house, claim-greeting-bonus).
- SP: `sp_service.award_sp/penalize_sp` (floor 0, dedup), role modules `sp_*`,
  `stage_award`, `dev_quality_sp`, `code_review_sp`.
- Games: `minigame_service` + bridge `POST /internal/colyseus/minigame-results`,
  backlash `/backlash-results`, races `/race-results` (all bridge-secret). None should
  touch `developer_xp` / `reward_events`.
- Quiz: `api/v1/quiz.py` (active, answers, reveal, leaderboard, daily, recap),
  `quiz_scoring.submit_answer`, review queue gated by `quiz:configure`.
- Celebrations: `services/celebrations/poster.post_digest` (ledger claim before Slack).

#### Features, cases, existing coverage, gaps

##### Sensitive details / reveal (employee_sensitive.py)
- Positive: HR and self read masked, reveal logs `field_revealed` (covered:
  `integration/test_employee_sensitive.py`).
- Negative: developer 403 (covered). GAPS: reporting manager 403 on read/reveal with no
  audit row; HR of another org gets 404 and nothing is logged in either org; unknown
  field 422; no-key 503 (covered).
- Corner: GAPS: clearing a value with "" (masked is_set false, reveal returns null but is
  still logged); unicode address round trip; reveal of a never-saved field.
##### Documents (employee_documents.py)
- Covered: upload/encrypt/delete rules, MIME sniff, 10 MB cap (`test_employee_sensitive.py`).
- GAPS: a reporting manager and another org's HR cannot list or open a document.
##### Birthdays / anniversaries (celebrations)
- Covered: who is announced, Feb 29 in common years, opt-out, settings audit
  (`integration/test_celebrations.py`), poster rules with fakes
  (`services/test_celebration_poster.py`, `test_celebration_review_fixes.py`).
- GAP: double-post prevention against a real ledger (two concurrent `post_digest`
  calls for the same day send exactly once; a second call reports `already_posted`).
##### XP ledger (xp_service) - no direct tests today
- Positive: award adds to total, writes one event, levels up at 100, publishes.
- Negative: zero/negative amount writes nothing; same source_ref twice awards once.
- Corner: fractional split (8.33) kept on the event, aggregate rounded; same source_ref
  in another org is a separate award; lost dedup race (unique index hit) leaves the
  total untouched; streak same day / next day / gap with an injected date.
##### SP ledger (sp_service)
- Positive/negative: award, dedup, zero is a no-op, penalty floors at 0, lost race
  restores the balance. Covered partly by `integration/test_sp_lifecycle.py`.
##### XP API (api/v1/xp.py) - no tests today
- me defaults; leaderboard is org-scoped and drops inactive users; history is own+org;
  vehicle unlock (unknown 400, insufficient 400, success, repeat 409); house upgrade
  (skip a tier 400, success); greeting bonus (once per pair, missing target 400).
- Suspected bug: greeting bonus accepts any target string (self, random ids, other orgs).
##### Games never award XP
- Covered: minigame handler with fakes (`api/v1/test_minigame_results.py`), race
  round trip (`integration/test_race_results_roundtrip.py`), service units.
- GAPS: real-DB bridge posts for minigame, backlash and race leave XP/SP untouched;
  wrong bridge secret 401; minigame cross-org 404; replay is idempotent.
- Suspected bug: bridge schema caps score at 1000 while Fishing/Pollen allow 6000.
##### Quiz answer-leak prevention
- Covered: grading, scoring math, schedule math, winner selection (unit).
- GAPS (real DB over HTTP): active quiz omits answer_key/explanation; submit returns
  only accepted/already_answered; double submit idempotent; reveal 403 before
  reveal_at, 200 after; another org's quiz 404; closed window 409; no XP written.
- Suspected bug: `/quiz/leaderboard/daily` exposes is_correct/points while open.

#### Coverage matrix

| feature | positive | negative | corner | existing test files | new test files |
|---|---|---|---|---|---|
| sensitive reveal | covered | +manager, +other org, +bad field | +clear, +unicode, +unset | integration/test_employee_sensitive.py | integration/test_employee_reveal_scope.py |
| documents access | covered | +manager, +other org | covered (size/type) | integration/test_employee_sensitive.py | integration/test_employee_reveal_scope.py |
| celebrations double post | covered (fakes) | covered | +real ledger, concurrent | integration/test_celebrations.py, services/test_celebration_*.py | integration/test_celebration_double_post.py |
| XP award ledger | new | new | new (fraction, cross-org, race, streak) | none | integration/test_xp_ledger.py, integration/test_xp_streak.py |
| SP award ledger | partial | new | new (floor, race) | integration/test_sp_lifecycle.py | integration/test_sp_ledger.py |
| XP API | new | new | new | none | integration/test_xp_api.py, integration/test_xp_spend.py |
| games never XP | partial | new | new | api/v1/test_minigame_results.py, integration/test_race_results_roundtrip.py | integration/test_games_award_no_xp.py |
| quiz leak | unit only | new | new | services/test_quiz_*.py | integration/test_quiz_answer_leak.py |

#### Outcome (what was actually added)

Test branch `test/people-gamification`: 9 new test modules, 53 test functions (+2 support
modules), all green without any fix. Fix branches each carry one product change and its
regression test (5 more test files, 12 test cases including parametrised ones).

| feature | positive | negative | corner | existing test files | new test files |
|---|---|---|---|---|---|
| sensitive reveal | covered | manager 403, other-org HR 404, bad field 422, bad PAN 422, no audit row on refusal | cleared value, unicode address, no alert for address | integration/test_employee_sensitive.py | integration/test_employee_reveal_scope.py |
| documents access | covered | manager 403, other-org HR 404 (list/open/delete) | doc survives refused delete | integration/test_employee_sensitive.py | integration/test_employee_reveal_scope.py |
| celebrations double post | real ledger | nobody -> day left open | two concurrent schedulers, two orgs same day | integration/test_celebrations.py, services/test_celebration_*.py | integration/test_celebration_double_post.py |
| XP award ledger | totals, level-up, publish | dedup, 0/-5/0.004 | 8.33 split, multiplier, per-org | none | integration/test_xp_ledger.py, (fix) test_xp_award_race.py |
| XP streak | day 1/2, x1.5 at day 7, SP at day 14 | same-day repeat | gap reset keeps best | none | integration/test_xp_streak.py |
| SP award ledger | balance, events | dedup, zero | floor at 0, first-ever penalty, lost race, per-org | integration/test_sp_lifecycle.py | integration/test_sp_ledger.py |
| XP API | me, leaderboard, history | sales role 403, no token 401 | max level, inactive + other-org excluded, zero-XP member | none | integration/test_xp_api.py |
| SP spending + greeting | vehicle, house, greeting | unknown/insufficient/repeat/skip tier, missing target | balance is per org | none | integration/test_xp_spend.py, (fix) test_greeting_bonus_target.py |
| games never XP | minigame, backlash, race recorded | bad secret 401, outsider 404 | replay idempotent, refused score keeps session | api/v1/test_minigame_results.py, integration/test_race_results_roundtrip.py | integration/test_games_award_no_xp.py, (fix) test_minigame_score_cap.py, (fix) test_race_results_org_members.py |
| quiz leak | active, submit, reveal after close, monthly board | other org 404, closed 409, future 409, reveal early 403, review queue 403 | right/wrong replies identical, no XP | services/test_quiz_*.py | integration/test_quiz_answer_leak.py, (fix) test_quiz_daily_board_reveal.py |

### Frontend

Scope: `frontend/src` stores, composables, utils and key components of the screens
redesigned in #390, plus #388 (Mermaid fallback). Vitest only: `*.test.ts` = node,
`*.spec.ts` = jsdom + SFC compile. Existing component specs stub Vuetify components
(no `createVuetify`), so new component specs follow that pattern. Baseline on main:
117 files / 867 tests green.

#### Features

##### Login and session (stores/auth.ts, views/LoginView.vue, services/api.ts)
- Positive: login stores access + refresh tokens, loads profile, honours
  `must_change_password`; request interceptor attaches the bearer token; a 401 refreshes once
  and retries with the new token; the refresh event updates the store's token.
- Negative: 401 login -> "Invalid email or password."; 422 -> validation sentences; network
  error; profile load failure after a good login; refresh fails -> tokens cleared + page
  remembered; 401 on `/auth/login` / `/auth/refresh` never refreshes; a retried request is
  not refreshed again; 403 "Password change required" -> change-password.
- Corner: concurrent 401s share one refresh; no refresh token -> straight to login;
  setup incomplete -> wizard; lookup unreachable then server back; blank fields never submit;
  logout clears error and remembered page.
- Existing: api.returnto.spec, api.formdata.spec, api.bloberror.spec, router/guards.spec,
  utils/afterSignIn.spec. Gaps: refresh flow, auth store, LoginView.

##### Permissions (usePermissions)
- Owner vs admin vs member role flags; permission-only gates; legacy bug fallbacks; signed out.
- Existing: none. Gap: whole composable.

##### Dashboard (stores/dashboard.ts, useDashboardOverview)
- Positive: tree data load, refresh param; overview loads BUDs, approvals count, time off.
- Negative: tree data error message; BUD list error; time-off error; no buds:view -> no fetch.
- Corner: time-off excludes WFH and rejected, sorts by start, caps at 4, window = today+21
  (frozen clock); non-approver -> pendingLeave null; connections fetched only when allowed.
- Existing: utils/dashboardOverview.test, useDashboardViewMode.spec. Gap: store + composable.

##### BUD board (useBudBoard)
- Columns follow phase order, discarded only on toggle; team filter matches nothing until
  members arrive; new notification refetches; filtering flag; one-time fetches on mount.
- Existing: utils/budBoard.test (pure filter). Gap: composable wiring.

##### BUD detail (useBudDetailLoader, useBudDetailTabs, useBudDetailActions,
useBudStatusTransitions, utils/budDetail)
- Tabs: values agree with deep-link set (`VALID_BUD_TABS` incl. uat/prod/closed),
  `STATUS_TAB_MAP` targets all valid; status change opens the stage tab; UAT off -> prod;
  edit/chat gating; design chat needs a design.
- Loader: valid `?tab=` wins, invalid ignored; overtaken load stops; reload.
- Actions: no-op without BUD; unchanged priority skipped; delete navigates only on success.
- Transitions: PR guards, override reason, pending manual cases, backend rejection snackbar,
  cancel agent/design.
- Existing: utils/budDetail.test, useBudStatusTransitions.test (close confirm, double click).

##### Leave (useLeaveRequestForm, stores/leave.ts, stores/leaveApprovals.ts)
- Form: payload rules per kind, debounced preview, stale preview dropped, reason does not
  re-preview, date clamps, half day only on a single day, canSend gating, reset to today.
- Store: errors returned as strings, refresh after create/cancel, older scope never wins,
  approvals badge falls back on failure.
- Approvals: approve/reject remove card and refresh badge, 409 sets notice and refetches,
  stale fetch ignored, pickers only remember unfiltered queue, withdraw/reschedule.
- Existing: leaveApprovalsStore.test (viewer reset, reversed range), ApprovalDecision.spec,
  LeaveTypePicker.spec, many utils/leave*.test.

##### Setup wizard (stores/setup.ts, setupSubmit.ts, useSetupChecklist, useRepoOnboard)
- Step validation, slug generation, navigation bounds, finalize idempotence + 409,
  payload shapes, error extraction; checklist polling/dismiss/reset; repo onboard error paths.
- Existing: setupSubmit.test (init idempotence, shim), useRepoOnboard.test (happy paths),
  utils/setupChecklist.test.

##### Mermaid (#388, useMermaidRender)
- Existing: quoted labels, valid diagram, syntax error -> source. Gap: `run()` throwing,
  one bad diagram among good ones, re-render guard.

#### Coverage matrix (final)

All paths under `frontend/src/`. Result: 137 files / 1083 tests green on `test/frontend`
(baseline 117 / 867); 186 new test declarations in 20 new files.

| feature | positive | negative | corner | existing test files | new test files |
|---|---|---|---|---|---|
| axios JWT + 401 refresh | token header, refresh+retry, event | refresh refused, no refresh token, auth URLs, other 403 | one refresh for concurrent 401s, no retry loop, password-change 403 on/off its page | api.returnto.spec, api.formdata.spec, api.bloberror.spec | services/api.refresh.spec.ts |
| auth store | login, tokens, profile, must-change | 401, 422 sentences, network, profile fail, change-password 401/400 | refresh event, empty event, logout forgets return page | router/guards.spec | stores/auth.spec.ts |
| LoginView | slug sign-in, home route, change-password route | wrong password callout | setup incomplete, unreachable then recovers, blank fields, stale error cleared | utils/afterSignIn.spec | views/__tests__/LoginView.spec.ts |
| usePermissions | owner/admin flags, HR leave, engineering | signed out, no permission list, role is not a permission | legacy bug fallbacks, reactive permission change | none | composables/usePermissions.test.ts |
| dashboard store + overview | loads, KPIs, approver queue | tree/BUD/time-off errors, no buds:view | frozen today, 21-day window, WFH/rejected out, cap 4, null vs 0 | utils/dashboardOverview.test | stores/dashboard.test.ts, composables/useDashboardOverview.spec.ts |
| BUD board | columns, filters, fetches | team without members matches nothing | discarded toggle, UAT off, notification count up vs down | utils/budBoard.test | composables/useBudBoard.spec.ts |
| BUD detail tabs | tab list, stage tab on status change | other BUD load keeps tab | every STATUS_TAB_MAP value valid; uat/prod/closed deep links; design chat needs a design | utils/budDetail.test | composables/useBudDetailTabs.test.ts |
| BUD detail loader | stage tab, channel, settings | unknown ?tab never applied | overtaken load stops, reload, failed load keeps tab | none | composables/useBudDetailLoader.test.ts |
| BUD actions | title, assignee, priority, delete | delete refused, refresh failure logged | no BUD loaded, unchanged priority | none | composables/useBudDetailActions.test.ts |
| BUD stage transitions | open PR, all merged, prod | refused PATCH snackbar, blank reason | pending cases from refreshed BUD, empty repo list needs reason, cancel agent/design | useBudStatusTransitions.test | composables/useBudStatusTransitions.guards.test.ts |
| BUD load error state | skeleton | error + retry + back | | none | components/buds/detail/__tests__/BUDDetailLoadState.spec.ts |
| leave dialog form | payload per kind, preview | problems, preview error | debounce, stale reply, reason no re-preview, reopen same, date clamps, half day | none | composables/useLeaveRequestForm.test.ts |
| leave store | create, cancel, preview, badge | error strings, no refresh on failure | older scope never wins, older failure ignored | leaveReports*.test | stores/leave.test.ts |
| leave approvals | approve/reject/withdraw/reschedule | 409 notice + reload, other failure, load error | stale fetch, pickers from unfiltered queue, notice cleared | leaveApprovalsStore.test, ApprovalDecision.spec | stores/leaveApprovalsDecide.test.ts |
| setup wizard store | step validation, navigation | invalid org/admin/repos | slug table, local-path develop rule, bounds | setupSubmit.test | stores/setupWizard.test.ts |
| setup submit | init + finalize payloads | detail/message/fallback/network errors | secret only for chosen mode, installable vs sourceCode shape, 409 finished, no double finalize | setupSubmit.test | stores/setupSubmitPayload.spec.ts |
| setup checklist | next step, live scan | poll failure | dismiss persists, reset brings back, polling stops, track once, unmount | utils/setupChecklist.test | composables/useSetupChecklist.spec.ts |
| bulk repo import | defaults, refresh keeps pick | list/branch/submit failures | missing default, develop as main, cap of 200, reset, owner deselect | useRepoOnboard.test | composables/useRepoOnboard.errors.test.ts |
| Mermaid (#388) | | run() throws -> source | one bad among good, failed/drawn not retried | useMermaidRender.spec | composables/useMermaidRender.failure.spec.ts |

Fix branches (regression tests live there, not on `test/frontend`):
- `fix/bud-detail-uat-off-tab`: composables/useBudDetailTabs.uatOff.test.ts
- `fix/repo-onboard-reselect-branch`: composables/useRepoOnboard.reselect.test.ts
- `fix/setup-slug-edge-hyphens`: stores/setupSlug.test.ts

### Multiplayer, shared world and the CLI

Branch `test/realtime-cli` (cut from origin/main c4303ebd). Runners: multiplayer vitest
(`multiplayer/src/**/*.test.ts`, also compiled by the multiplayer `tsc` build in CI), frontend
vitest node project (`frontend/src/**/*.test.ts`, the only runner that already covers
`shared/world` and `shared/race`), CLI vitest (`cli/src/**/*.test.ts`, run on ubuntu, windows
and macos by `cli-quality.yml`; `cli-e2e.yml` drives the real lifecycle against Docker on Linux).

#### Multiplayer

| Feature | Positive | Negative | Corner |
| --- | --- | --- | --- |
| Bridge endpoint `/internal/publish` | org event delivered to registered room; room-scoped decline routed | missing / wrong / different-length secret -> 401; missing type, both or neither of orgId/roomId -> 400; unknown room-scoped type -> 400; decline without userId -> 400 | no active room -> 200 delivered=false; room handler throws -> 500; newline in type does not reach the log line raw |
| `safeLog` | plain strings unchanged | null / undefined placeholders | CR, LF, U+2028/2029 escaped; 500-char cap; non-string values |
| Race / Backlash registries | dispose fires once then unregisters; phase keeps registration | unknown roomId is a no-op | throwing callbacks contained (race + backlash summary hooks) |
| OrgRoom `onAuth` | verified identity replaces client claims | prod + no token rejected; invalid token, backend down, backend HTTP error rejected with distinct messages; token of another org rejected | dev mode accepts tokenless join |
| OrgRoom messages | takeover start/end, move by controller, mount allowlisted vehicle, house tier 1..3 | takeover of someone else, move by non-controller, invalid anim, NaN/Infinity, unknown vehicle, tier 0/4 | move rate limit (25 ms), interior hand-off on takeover_end, malformed member_presence bridge payload dropped |
| MinigameRoom | verified identity, score posted once with server score | unknown game -> mg_error; prod tokenless rejected; org mismatch rejected | malformed mg_input ignored; endGame idempotent; no userId -> recorded=false without a POST |
| RaceRoom lobby | host start with MIN_RACERS, host cancel, host add invitees | non-host start/cancel/add; join after lobby; join beyond MAX_RACERS; malformed join | add-invitees dedupe and MAX_RACERS cap; decline removes invitee only in lobby |

Existing: `BacklashRoom*.test.ts`, `OrgBacklashHandler.test.ts`, `OrgRaceHandler.test.ts`,
`RaceBotDriver.test.ts`, `RaceRoomHelpers.test.ts`, `backlash/BacklashEngine.test.ts`,
`minigame/*.test.ts`, `sim/CoffeeBarPhase.test.ts`, `sim/InferredPresenceSim.test.ts`.
Gaps before this work: bridge endpoint, log sanitiser, registries, OrgRoom auth and message
handlers, MinigameRoom room logic, RaceRoom lobby authority.

#### Shared world (frontend node project)

Existing tests pin baseline coordinates (zones, paths, trees, hub anchor, layout scale curve).
Gaps: invariants across repo counts (no zone overlap, rim gap preserved, routes connect hub to
every zone, trees inside the orchard and distinct, determinism), village layout invariants
(distinct houses, inside fence bounds, housing clear of coffee bar), break-seat layouts,
house-tier fallback.

#### CLI

| Feature | Positive | Negative | Corner |
| --- | --- | --- | --- |
| config | write/read round trip | missing config message, unsupported version | path built with the platform separator |
| docker runner | compose v2 preferred, cached | ENOENT -> friendly message; neither compose -> error | falls back to docker-compose v1 |
| preflight | passes when docker + daemon + compose | docker missing, daemon down | - |
| health | backend ok + frontend serving | backend status != ok, frontend 5xx, fetch throws | deadline respected (fake timers) |
| init | writes compose, .env (0600 on POSIX), config, .gitignore; pulls | declined re-run changes nothing; corrupt .env aborts before writing | re-run keeps secrets and a custom .gitignore; pull failure only warns |
| start/stop/status/logs/reset/update | compose args per command | missing config; compose failures set exit code; reset declined | update --tag pins tag; update rewrites legacy image names; BODHIORCHARD_PULL |

Existing: `compose.test.ts`, `docker.test.ts` (pull policy), `env.test.ts`, `ports.test.ts`,
`project.test.ts`, `resolve.test.ts` (toContainerHost), `secrets.test.ts`.

#### Coverage matrix (final)

| feature | positive | negative | corner | existing test files | new test files |
| --- | --- | --- | --- | --- | --- |
| Bridge endpoint | yes | yes | yes | none | bridge/BridgeEndpoint.test.ts |
| safeLog | yes | yes | yes | none | bridge/logSanitize.test.ts; fix branch: bridge/logSanitize.lineBreaks.test.ts |
| Race/Backlash registries | yes | yes | yes | OrgRaceHandler.test.ts (partial) | bridge/registries.test.ts |
| OrgRoom auth | yes | yes | yes | none | rooms/OrgRoomAuth.test.ts; fix branch: rooms/VerifiedJoinIdentity.test.ts |
| OrgRoom messages | yes | yes | yes | none | rooms/OrgRoomMessages.test.ts; fix branch: rooms/MalformedPayloads.test.ts |
| OrgRoom bridge events + snapshot | yes | yes | yes | sim tests only | rooms/OrgRoomBridgeEvents.test.ts |
| MinigameRoom | yes | yes | yes | minigame/MinigameEngines.test.ts (engines only) | rooms/MinigameRoom.test.ts |
| RaceRoom lobby + inputs | yes | yes | yes | RaceRoomHelpers.test.ts, RaceBotDriver.test.ts | rooms/RaceRoomLobby.test.ts; fix branch: rooms/RaceRoomRacerIdentity.test.ts |
| Room matchmaking partition | yes | yes | yes | none | fix branch: roomDefinitions.test.ts |
| HouseRoom move | yes | yes | - | none | fix branch: rooms/MalformedPayloads.test.ts |
| Shared zones/paths/trees across N | yes | yes | yes | zones/paths/treePositions regression tests (baseline only) | frontend engine/world/worldInvariants.test.ts |
| Village / break seats / house tiers | yes | yes | yes | VillageLayout.test.ts | frontend engine/world/villageInvariants.test.ts |
| CLI config | yes | yes | yes | none | cli lib/config.test.ts |
| CLI docker runner | yes | yes | yes | docker.test.ts (pull policy) | lib/docker.runner.test.ts, lib/docker.fallback.test.ts |
| CLI preflight / health | yes | yes | yes | none | lib/preflight.test.ts, lib/health.test.ts |
| CLI init | yes | yes | yes | project.test.ts (keyring) | commands/init.test.ts |
| CLI start/stop/status/logs/reset/update | yes | yes | yes | none | commands/lifecycle.test.ts |

Not covered: CoffeeBarRoom / CafeteriaRoom room logic (only their phase machines are tested),
OrgRaceHandler / OrgBacklashHandler matchMaker paths, CLI resolve.ts prompts and reuse probes,
CLI index.ts error translation (module runs parseAsync on import), race physics beyond the
existing RacePhysics/RaceTrackFeatures suites.

## Bugs found and fixed

Each fix is its own pull request with the regression test that caught it. Every regression
test fails on main and passes with its fix.

| Area | Bug | PR |
| --- | --- | --- |
| Test suite | Four integration modules ran in the Docker-free pass and never under `-m integration` | [#419](https://github.com/mickyarun/glideship/pull/419) |
| Auth | Deleting a role members still hold answered 500 | [#417](https://github.com/mickyarun/glideship/pull/417) |
| Auth | BUD and todo assignees could be users from another org | [#418](https://github.com/mickyarun/glideship/pull/418) |
| Setup | Branch detection matched prefixes (`devops` taken for `dev`, `main-legacy` for `main`) | [#403](https://github.com/mickyarun/glideship/pull/403) |
| Setup | `.` and `..` passed the cloner's name check; purging `..` deleted every org's clones | [#404](https://github.com/mickyarun/glideship/pull/404) |
| Setup | One unreadable folder made the whole picker answer 403 | [#405](https://github.com/mickyarun/glideship/pull/405) |
| Setup | A NUL byte or over-long name in a repo path answered 500 | [#406](https://github.com/mickyarun/glideship/pull/406) |
| Setup | The same checkout named twice started two scans of one repo | [#407](https://github.com/mickyarun/glideship/pull/407) |
| BUD | Two BUDs created at once in one org: the second failed with 500 | [#427](https://github.com/mickyarun/glideship/pull/427) |
| BUD | Two writers of one BUD at once: double close side effects or a 500 on history numbering | [#428](https://github.com/mickyarun/glideship/pull/428) |
| BUD | Auto-close always recorded "prod -> closed" | [#429](https://github.com/mickyarun/glideship/pull/429) |
| BUD | Auto-close never wrote learning metrics (the error was swallowed) | [#430](https://github.com/mickyarun/glideship/pull/430) |
| MCP | `write_bud_design` wrote onto another org's BUD or repo | [#408](https://github.com/mickyarun/glideship/pull/408) |
| MCP | A long User-Agent, forwarded address or tool name left no audit row | [#409](https://github.com/mickyarun/glideship/pull/409) |
| MCP | A call whose database write failed was never audited | [#410](https://github.com/mickyarun/glideship/pull/410) |
| Jobs | A job cancelled while queued still ran, from the UI's cancel buttons too | [#411](https://github.com/mickyarun/glideship/pull/411) |
| Bugs | Bugs could link to another org's BUD or feature or be assigned outside the org; bad ids answered 500 | [#431](https://github.com/mickyarun/glideship/pull/431) |
| Bugs | `rejectedAt` was always null in responses | [#432](https://github.com/mickyarun/glideship/pull/432) |
| Triage | Two concurrent decisions on one triage session (API or Slack reactions) | [#433](https://github.com/mickyarun/glideship/pull/433) |
| Triage | A severity like "High" or "P1" from the agent crashed Slack bug approval | [#434](https://github.com/mickyarun/glideship/pull/434) |
| Triage | Anyone, even outside the org, could discard a Slack bug report | [#435](https://github.com/mickyarun/glideship/pull/435) |
| Gamification | A duplicate XP award that lost a race still paid | [#412](https://github.com/mickyarun/glideship/pull/412) |
| Gamification | The greeting bonus paid for any target, including yourself or a made-up id | [#413](https://github.com/mickyarun/glideship/pull/413) |
| Gamification | Fishing and Pollen Pop scores over 1000 were refused and lost | [#414](https://github.com/mickyarun/glideship/pull/414) |
| Gamification | The per-quiz board showed who was right while the quiz was open | [#415](https://github.com/mickyarun/glideship/pull/415) |
| Gamification | Race results stored users from another org | [#416](https://github.com/mickyarun/glideship/pull/416) |
| Frontend | A BUD in UAT with UAT turned off opened on a blank tab | [#394](https://github.com/mickyarun/glideship/pull/394) |
| Frontend | Re-ticking a repo in bulk import lost its default branch | [#395](https://github.com/mickyarun/glideship/pull/395) |
| Frontend | The generated org slug could end with a hyphen the wizard then rejected | [#393](https://github.com/mickyarun/glideship/pull/393) |
| Frontend | A slow load of the previous BUD could replace the BUD on screen | [#396](https://github.com/mickyarun/glideship/pull/396) |
| Frontend | An unknown `?tab=` link kept the previous BUD's tab | [#397](https://github.com/mickyarun/glideship/pull/397) |
| Multiplayer | A message with no payload crashed the whole server | [#398](https://github.com/mickyarun/glideship/pull/398) |
| Multiplayer | Org and mini-game rooms took the join identity from the client, not the token | [#399](https://github.com/mickyarun/glideship/pull/399) |
| Multiplayer | Race rooms had no join auth and inputs could drive any racer | [#400](https://github.com/mickyarun/glideship/pull/400) |
| Multiplayer | Log sanitising missed Unicode line breaks | [#401](https://github.com/mickyarun/glideship/pull/401) |
| Multiplayer | Org, coffee bar, cafeteria and house rooms were shared across orgs and houses | [#402](https://github.com/mickyarun/glideship/pull/402) |

## Open questions

These need a product decision. No test asserts either behaviour.

Access and security:
- The repo write endpoints in `settings_repos.py` (clone, delete, branch and status changes,
  classify, extract routes) need only engineering access, so a developer with `settings:view`
  can remove a repo. Add-by-path, finalize and the picker need `settings:edit` since [#389](https://github.com/mickyarun/glideship/pull/389).
- `GET/POST /api/v1/jobs/{id}` don't check the job's org; the job id is the access key.
- Any per-user MCP token can call all 29 tools on `/mcp/tools/*`, including `write_bud` (no
  assignee or closed-status check), `post_slack_message` and `get_team_context`.
- The monthly quiz board (`GET /quiz/leaderboard`, used by the frontend) updates points and
  correct counts at submit time, so players can tell whether an answer was right while the
  quiz is open. Options: accept it, leave open quizzes out of the board, write scores at
  reveal time, or show only participation until reveal.
- `GET /organizations/{id}` returns the raw org config (encrypted Jira token, calendar key,
  Slack status secret as ciphertext) to every member.
- No logout or token revocation, a password change doesn't end other sessions,
  change-password doesn't ask for the current password, and there is no login rate limit.
- Inviting an email that exists in another org answers 500 and reveals the email exists.
  Login matches email case-sensitively. Member deactivate and set-password act on the user
  across every org they belong to.
- The cloner's docstring says the token is never written to disk, but it stays in the
  clone's `.git/config` origin URL.
- The Claude connection test accepts a typed `base_url` from developers, and the Jira
  `site_url` isn't validated, so the backend can be pointed at any host.
- `_mask_secret` shows the first and last four characters, which is most of a short secret.
- Two concurrent init-org calls could create two orgs.
- Multiplayer coffee bar, cafeteria and house rooms have no join auth; `upgrade_house` trusts
  the client's tier; `fetchOrgSnapshot` puts the org id into the URL unescaped.
- The MCP rate limiter keys on the client-supplied `X-Forwarded-For`.

Behaviour:
- `DELETE /buds/{id}` answers 500 when a bug or a learning row references the BUD. A fix needs
  a migration (SET NULL on bugs and CASCADE on learnings, or a 409 pointing to discard).
- CLAUDE.md says closing moves linked features `in_progress -> done`; the code leaves them.
- Closing from testing pays the 50 XP completion award plus contributor XP and SP; the award
  goes to whoever is assigned at prod after the round-robin; auto-close from UAT pays none.
- The manual-test-case gate only runs when leaving testing; QA results stay editable after
  close.
- Chat edits to the tech spec during development can't be reverted from History (409), and
  revert rewinds the whole BUD rather than one section.
- The BUD-number lock is held until the create commits, including Slack calls on the intake
  path, so creates in one org are serialised.
- Repos saved with a wrong main or develop branch by the old detection are not repaired, and
  the remote branch list now shows origin's branches only.
- The bug linker can match closed or discarded BUDs; deactivated members can be assigned bugs;
  Jira import sets assignees without a membership check; two orgs tracking the same GitHub
  repo make webhook lookup ambiguous; `%` and `_` act as wildcards in feature search;
  non-ASCII titles make odd tags; P0/P1 severities fall back to medium.
- `triage_sessions.status` and the Jira import status columns are strings, not Postgres
  enums.
- About ten MCP handlers answer 500 for badly typed params (a string `limit`, a non-UUID
  `repo_id`, an out-of-range `bud_number`). A shared coercion helper would fix the class.
  `create_bud` silently drops a feature id from another org.
- The [#388](https://github.com/mickyarun/glideship/pull/388) tech-planner rule reaches only orgs seeded after it; stored prompts aren't
  refreshed.
- Leave: a skip-level manager doesn't see the leave type on the team calendar; the report
  range check allows 366 days in some years.
- Frontend: login with no org slug stops silently; one-character slugs pass; a failed
  code-review status check reads as "no open PR"; `?tab=learnings` isn't a deep link.
- The village fence reaches into the coffee bar zone at 25 or more members; race lobby
  leavers keep their slot; re-running `glideship init --yes` remaps ports in use by its own
  stack and resets a pinned tag; `update --tag` writes the tag before failing on secrets.
- Race results don't check the host's membership; the greeting target only has to be a
  member, not an active user; `/v1/jobs/{id}/cancel` on a queued agent job stops it but
  leaves its task row non-terminal.

Test suite:
- Some routes start background work on the app's own database session instead of the test
  one (leave notifications, the deferred estimator). The new tests stub these, and the BUD
  tests fail closed if anything connects, but a guard in the integration conftest would need
  the existing tests to stub them first.

## Not covered yet

- A full scan run end to end (real worktrees, indexer and synthesis); mocked unit tests cover
  the stages.
- `bud_agent_handler.py`, `job_utils.py`, `job_agents.py`, `background.py` and `claude_env.py`,
  the `/mcp/sse` heartbeat re-auth, and the org scope of `write_feature_registry`.
- GitHub App flows (bulk onboard, installable repos, members), the Slack member endpoints, the
  AI provider check success paths, Jira import internals and the design-system extractor run.
- Role-specific SP modules beyond the lifecycle tests, the quality bonus, the 30-day streak
  milestone, and the quiz scheduler, rollup and review transitions.
- Full view mounts of the dashboard, board, BUD detail and leave dialog, `useBudDetailChat`,
  the socket layer and the BUD store's other network actions.
- Coffee bar and cafeteria room logic, the race and backlash matchmaking paths, and the CLI's
  port prompts and entry point.
- Calendar backfill and the digest and Slack status scheduler loops, the code review override
  while an agent task runs, and concurrent init-org.
