# Cross-Repo Feature Merge — scanv2 Final Stage

> **Plan persistence**: this file lives at `~/.claude/plans/we-are-now-merging-happy-quasar.md` (ephemeral). A frozen copy is kept at `bodhiorchard/docs/plans/cross-repo-feature-merge.md` so it survives `/clear` and shows up in git history.

> **Status (2026-04-27)**: Phase 0 (POC) **executed and complete**. Phase 5 (GitNexus contract pre-link) **dropped** — POC measurements on the 19-repo ATOA dataset failed two of three thresholds. See "Phase 0 results" below for numbers. Phases 1–4 are the active scope going forward.

## Phase 0 results (POC — concluded 2026-04-27)

Built `atoa-poc` group from 15 of 19 active DB repos (4 not yet indexed in GitNexus: `ATOAFraud`, `AtoaFraudCheck`, `AtoaIntegration`, `atoa_pax`). Ran `gitnexus group sync` and computed contract-to-feature overlap.

| Threshold | Required | Measured | Pass? |
|---|---|---|---|
| `group sync` wall-clock | < 90 s | **17.6 s** | ✓ |
| Match rate (cross-links / contracts) | ≥ 40% | **1.33%** (9/677) | ✗ |
| Real match rate (excl. spec/test files) | informational | 0.15% (1/677) | — |
| Feature coverage (would-pre-link pairs / active features) | ≥ 30% | **18.77%** (49/261) | ✗ |

**Why so low**: ATOA's microservices use runtime-configured base URLs (env vars / service discovery), so GitNexus's exact-match Contract Bridge can't normalize them. 8 of 9 cross-links were spec-file noise (`http.utils.spec.ts` matching `GET /` against every repo's root controller); only 1 was a real link (`ATOAPayment::PaymentsExecutePaymentService.ts → AtoaOpenBanking::vrp-payment.controller.ts` via `POST /payments`). The brainstorm's "structurally-disconnected services" caveat turned out to dominate this codebase.

**Decision**: drop Phase 5. The remaining 4 phases (1–4) are unaffected.

**POC artefacts left in place** (delete-in-one-step when convenient):
- `backend/scripts/poc_gitnexus_group/` — README, `01_build_group.sh`, `02_measure_sync.sh`, `_resolve_repos.py`, `_metrics.py`, `03_overlap_report.py`, `output/` (raw + report JSON)
- `backend/app/api/v1/poc.py` + 1-line include in `app/api/router.py`
- `frontend/src/views/settings/code/{PocGitNexusReport.vue, PocGitNexusMetric.vue, pocReport.ts}` + route in `router/index.ts` + "POC report" link in `SettingsCode.vue`
- GitNexus group: `~/.gitnexus/groups/atoa-poc/`

The POC report UI works end-to-end at **Settings → Code → POC report** for retrospect/reference. Recommend deleting the POC layer in a clean-up commit before Phase 1 starts (or leave until Phase 4 lands and tear down everything POC-related at once).

## Context

scanv2 (per-repo pipeline) and the new "Settings → Code" UI are merged. The last remaining piece is robust **cross-repo feature merge**. The existing `phase_b3_merge` (`backend/app/scan/global_/feature_merge.py`) has the right shape — immutable `synthesized_features` audit, `KnowledgeItem` post-merge view, MCP-driven LLM consolidation — but two real bugs and three over-engineered parts:

| # | Issue | Fix |
|---|---|---|
| B1 | `is_workspace=False` skips merge → **new repo added later never joins existing canonicals** | Gate on distinct active repos org-wide ≥ 2 |
| B2 | `merge_features` matches by mutable title → silent no-ops on rename/collision | New id-keyed `apply_feature_merge_plan` MCP tool |
| O1 | 3-pass × 500-batch loop sized for 200K Sonnet 4.5 | One call fits 16K features at 1M; loop only when overflowing |
| O2 | Static `merge_model = opus-4-6` for every scan | Auto-switch Sonnet 4.6 → Opus 4.7 by feature count |
| O3 | Flat "find duplicates among all" prompt is O(N²) reasoning | Two-section prompt: NEW vs EXISTING canonicals |

Verified facts (Apr 2026, Anthropic docs + GitNexus ARCHITECTURE.md):
- Sonnet 4.6 and Opus 4.7 both ship 1M-token context at standard pricing.
- GitNexus `group_sync` cross-links repos via HTTP/topic **contracts only** — communities stay per-repo, so a fully-monolithic GitNexus path can't replace LLM merge.
- Current DB: 131 active features (100x below the 16K single-call ceiling).

## Approach (changes by area)

### A. Gate (B1)
Replace `is_workspace and total_features_synthesized >= 2` with one SQL question:
```sql
SELECT count(DISTINCT krl.repo_id)
FROM knowledge_repo_links krl
JOIN knowledge_items ki ON ki.id = krl.knowledge_id
WHERE ki.org_id=:org AND ki.category='feature_registry' AND ki.is_active;
```
≥ 2 → merge runs. Fixes the new-repo-added-later case automatically.

### B. Two-section incremental prompt (O3)
Partition the merge prompt into:
- **EXISTING canonicals** (lean rows: `[k_id] "title" (repos) · clusters`)
- **NEW features in this scan** (enriched: + description, capabilities, top file paths)

Instructions ask Claude to decide MERGE / LINK / CREATE *for each NEW feature*, not to re-cross-check existing canonicals. Cuts reasoning cost and isolates failure mode (timeout = orphan new features, never disturbs existing canonicals).

### C. Id-keyed structured ops (B2)
New MCP tool `apply_feature_merge_plan` accepting `{ops: [{action, canonical_id, absorb_ids, repo_ids, ...}]}`. Backend handler executes merge / create / link in one transaction. Drops the title-match fragility.

### D. Context-budget candidate selection (O1, O2)
- ≤ `SAFE_FEATURE_BUDGET (16000)` features → single Claude call.
- > 16000 → embedding-blocked clusters via new `feature_clusterer.py` (pgvector ANN + union-find at cosine ≥ 0.75, with title normalization for recall).
- Per-call model: Sonnet 4.6 for ≤ `SONNET_QUALITY_BUDGET (3000)` features, else Opus 4.7. Cluster size > `LARGE_CLUSTER_OPUS (200)` also escalates.

### E. GitNexus contract pre-link (optional, flagged)
Behind `settings.scan.use_gitnexus_pre_link = False`. If a `group.yaml` exists, run `group_sync` and walk `group_contracts` to pre-link contract-coupled features (frontend↔backend) before invoking LLM merge. Contract Bridge is exact-match HTTP/topic only, so this is a partial win — keeps LLM merge for the structurally-disconnected long tail.

### F. Single-repo path (no code change)
Synthesis already writes to `knowledge_items` via `synth_feature_writer.persist_synth_feature`. Post-merge audit already stamps the lone row CANONICAL. Just lock with a regression test.

## Phased TODO

Each phase is its own commit. Pause for user review at the gate before moving on.

### Phase 0 — POC: GitNexus group on all 19 repos + small report UI  ✅ DONE (2026-04-27)
**Verdict: Phase 5 dropped.** Match rate 1.33% (req ≥40%), feature coverage 18.77% (req ≥30%). Sync time 17.6s passed. See "Phase 0 results" at top of plan for full numbers, root cause (runtime-configured base URLs in ATOA microservices), and POC artefact locations.

**Scope (historical)**: validate the GitNexus pre-link assumption (and measure community/sync cost) on the real 19-repo ATOA dataset *before* committing to the rest of the plan. Throwaway code is acceptable, but lives in a clearly-marked POC dir so it can be deleted in one step if results don't justify Phase 5.

**The 19 repos** (active in `tracked_repositories`):
ATOABatch, AtoaChromeExtension, AtoaCommunication, ATOAConsumerWebNew, ATOACore, ATOAFraud, AtoaFraudCheck, AtoaIntegration, ATOAMerchantapp, ATOAMerchantDashboard, AtoaOpenBanking, atoa_pax, ATOAPayment, AtoaPaymentProcessor, ATOAPaymentReconsiliationService, AtoaReviewSystem, AtoaShortlinks, ATOA_VA, ATOAWebhook.

**What we measure** (and the answers we want):

| Metric | Source | What we learn |
|---|---|---|
| Per-repo Leiden community count | `gitnexus status` per repo / `gitnexus://repo/{name}/clusters` | How fragmented each repo's structure is — confirms communities are per-repo (not cross-repo) |
| Per-repo Leiden run time (analyze) | timed `npx gitnexus analyze <path>` | Cost of indexing if we ever auto-refresh |
| Total `group sync` time | timed `npx gitnexus group sync atoa` | Whether pre-link is fast enough to run on every scan |
| Total contracts extracted | `group contracts atoa --json` count | How much HTTP/topic surface area exists across the suite |
| Cross-link count (matched contracts) | same JSON, `cross_link != null` filter | Pre-link recall ceiling — upper bound on Phase 5's value |
| Unmatched contracts | `group contracts atoa --unmatched-only` count | Where the LLM merge will still need to do work |
| Contract → existing feature overlap | Python script: walk contracts, prefix-match against `synthesized_features.code_locations` | How many of today's 131 features the pre-link could attach without an LLM call |

**POC steps**:

- [x] Create `backend/scripts/poc_gitnexus_group/` (throwaway POC dir, marked in README)
- [x] `01_build_group.sh` — built atoa-poc with 15 of 19 repos (`ATOAFraud`, `AtoaFraudCheck`, `AtoaIntegration`, `atoa_pax` not yet GitNexus-indexed). 6,442 total Leiden communities across the 15.
- [x] `02_measure_sync.sh` — sync ran in 17.6 s; produced 677 contracts (632 HTTP, 45 gRPC), 9 cross-links.
- [x] `03_overlap_report.py` — split into `_metrics.py` + orchestrator (200-line ceiling). Verified threshold misses.
- [x] **Report UI** — `PocGitNexusReport.vue` (188 lines) + `PocGitNexusMetric.vue` (21) + `pocReport.ts` (78). Live at Settings → Code → "POC report".
- [x] `backend/app/api/v1/poc.py` (58 lines) — `GET /api/v1/poc/gitnexus-group-report`. Wired in `app/api/router.py`.
- [x] **Decision applied**: 2 of 3 thresholds missed → **Phase 5 dropped**.
- [x] **Code-review gate passed**: ruff zero, vue-tsc zero, mypy clean on POC files (126 pre-existing errors in unrelated files unchanged), every POC file ≤ 188 lines, no hardcoded paths, all artefacts quarantined.
- [x] User review — completed; user instructed plan to record Phase 5 drop and prepare for Phase 1.

### Phase 1 — Gate fix (B1) + delete dead `is_workspace` plumbing + audit-only path test
**Scope**: smallest possible change that ships the new-repo-added-later fix and removes a vestigial flag.

**Why delete `is_workspace`**: traced every use. Only one is load-bearing today (the merge gate, which is the bug). Everywhere else it's either dead (`prompts.py:56` does `del is_workspace`) or cosmetic (`scan_repo_loop.py:106` log line — replace with inline `total_repos > 1`). After the gate moves to an org-wide query, the flag has no purpose.

- [ ] `gitnexus_impact({target: "phase_b3_merge", direction: "upstream"})` — confirm callers, report risk
- [ ] `gitnexus_impact({target: "_collect_feature_dicts", direction: "upstream"})`
- [ ] `gitnexus_impact({target: "phase_b2_synthesis", direction: "upstream"})` — covers the synthesis arg
- [ ] Add `KnowledgeItemRepository.distinct_active_repo_count(category) -> int` (~10 lines)
- [ ] `phase_b3_merge`: replace `is_workspace and total_features_synthesized >= 2` with `await ki_repo.distinct_active_repo_count("feature_registry") >= 2`. Drop the `is_workspace` parameter from the function signature
- [ ] `reposcanv2/stages/feature_merge.py`: drop the `is_workspace = …` line and the `is_workspace=` kwarg in the `phase_b3_merge` call
- [ ] `reposcanv2/global_phases.py:74`: stop writing `"is_workspace": len(repo_paths) > 1` into the config dict
- [ ] `services/scan_pipeline.py:124`: delete `is_workspace = len(repo_paths) > 1`; update its 3 downstream call sites (lines 184, 257, 285)
- [ ] `services/scan_repo_loop.py:79,106`: drop the `is_workspace` parameter; replace the log condition with inline `total_repos > 1`
- [ ] `scan/global_/feature_synthesis.py:53,68,143`: drop `is_workspace` from `phase_b2_synthesis` signature and from the `build_synthesis_prompt` call
- [ ] `scan/prompts.py:41,56`: delete the `is_workspace` parameter and the `del` line from `build_synthesis_prompt`
- [ ] Grep `is_workspace` → expect zero matches in `backend/app/`
- [ ] Tests: extend `tests/scan/test_feature_merge.py` with single-repo-CANONICAL + new-repo-added-later cases
- [ ] **Code-review gate**:
  - `ruff check . --fix && ruff format . && mypy app/` → zero warnings (memory: lint_zero)
  - All files touched < 200 lines (memory: code_principles)
  - No hack / hardcode / dead branch
  - `gitnexus_detect_changes()` — only listed symbols changed
- [ ] User review — pause

### Phase 2 — Id-keyed `apply_feature_merge_plan` MCP tool (B2)
**Scope**: introduces the new MCP tool; legacy `merge_features` stays for one release as a deprecation shim.

- [ ] `gitnexus_impact({target: "handle_merge_features", direction: "upstream"})`
- [ ] `app/repositories/knowledge_item.py`: add `transfer_repo_links_bulk(absorb_ids, canonical_id)` and `add_repo_links(knowledge_id, repo_ids)` (skip if equivalents exist)
- [ ] `app/mcp/handlers_knowledge.py`: add `handle_apply_feature_merge_plan(payload)` — atomic merge / create / link executor (~80 lines, in its own helper file if the module exceeds 200 lines)
- [ ] `app/mcp/server.py`: register `apply_feature_merge_plan` tool with JSONSchema
- [ ] `app/mcp/synth_feature_writer.py::apply_merge_outcomes`: extend to take `canonical_knowledge_id` + `absorb_knowledge_ids` (id-based audit stamping)
- [ ] Mark `handle_merge_features` deprecated; add log warning
- [ ] Tests: each op type + cross-org canonical_id rejection (rollback assertion)
- [ ] **Code-review gate**: ruff/mypy zero, ≤ 200 lines/file, gitnexus_detect_changes
- [ ] User review — pause

### Phase 3 — Two-section prompt + auto-switch model (O2, O3)
**Scope**: rewires `_collect_feature_dicts` and `build_merge_prompt` and the model selection.

- [ ] `app/config.py::LLMConfig`: replace single `merge_model` with `merge_model_default = "claude-sonnet-4-6"`, `merge_model_large = "claude-opus-4-7"`. Add `merge_safe_feature_budget=16000`, `merge_sonnet_quality_budget=3000`, `merge_large_cluster_opus=200`. Deprecate `merge_batch_size` (still read for back-compat one release)
- [ ] `_collect_feature_dicts`: also return `KnowledgeItem.id`, `cluster_names`, top-2 `code_locations` paths. Split into `existing_canonicals` and `new_features` by joining to `synthesized_features.scan_id`
- [ ] `build_merge_prompt`: render two-section EXISTING/NEW prompt, id-keyed rows, instruct Claude to call `apply_feature_merge_plan`. Single-section degenerate path for no-prior-canonicals
- [ ] `phase_b3_merge`: introduce `pick_merge_model(feature_count)`; per-call model resolution
- [ ] Replace 3-pass × 500-batch loop with a single iteration over candidate_groups (Phase 4 introduces multi-group case)
- [ ] Tests: prompt golden-file (covers both sections + degenerate); model-pick boundary tests at 2999 / 3000 / 3001 features
- [ ] **Code-review gate**: ruff/mypy zero, every modified file ≤ 200 lines (split helpers if not), gitnexus_detect_changes
- [ ] User review — pause

### Phase 4 — Embedding clusterer for >16K-feature path (O1)
**Scope**: extreme-scale fallback. Only kicks in above 16K active features (15× current).

- [ ] `app/services/feature_clusterer.py` — NEW (~120 lines):
  - Load active feature embeddings (already populated by `embed_missing_items`)
  - Title normalize: lowercase, strip plurals, tiny synonym table (Auth↔Authentication, DB↔Database, UI↔Interface) — keep table in same file, ≤ 30 entries
  - pgvector ANN: `ORDER BY embedding <=> $vec LIMIT 8` per feature, keep cosine ≥ 0.75
  - Union-find connected components → list of clusters; singletons skipped
- [ ] `phase_b3_merge`: branch to `build_candidate_clusters` when `active_count > SAFE_FEATURE_BUDGET`
- [ ] Safety net: if cluster path produces no merges, run a single fallback whole-list pass (guards clusterer false negatives at small N)
- [ ] Tests: 16001-feature seeded fixture; assert call count = cluster count, singletons stay CANONICAL
- [ ] **Code-review gate**: ruff/mypy zero, ≤ 200 lines, gitnexus_detect_changes
- [ ] User review — pause

### Phase 5 — Optional GitNexus contract pre-link (E)  ❌ DROPPED (2026-04-27)
**Reason**: Phase 0 POC measured match_rate=1.33% (req ≥40%) and feature_coverage=18.77% (req ≥30%) on the 19-repo ATOA dataset. ATOA's microservices use runtime-configured base URLs, so GitNexus's exact-match Contract Bridge can't normalize them. See top-of-plan "Phase 0 results" for full numbers.

If the assumption changes (e.g., a different org with declared HTTP contracts and no env-var URL config) the original scope below can be revisited:

> Only for orgs with a `group.yaml`. Default-off feature flag.
> - `app/config.py::ScanConfig`: add `use_gitnexus_pre_link: bool = False`
> - `app/scan/global_/contract_pre_link.py` — NEW (~150 lines, split into helpers if > 200):
>   - Detect `group.yaml` present in workspace; if absent, no-op
>   - Call `group_sync` then `group_contracts`
>   - Walk pairs; resolve to features via `code_locations` prefix match
>   - Attach `KnowledgeRepoLink` only when both sides resolve to a single feature; punt ambiguous pairs to LLM merge
> - `phase_b3_merge`: call pre-link before the LLM branch (gated on flag)
> - Tests: contract→feature resolver unit; ambiguous-pair punt test

## Files touched (consolidated)

| File | Purpose | Phase |
|---|---|---|
| `backend/app/scan/global_/feature_merge.py` | gate + loop replacement + per-call model | 1, 3, 4 |
| `backend/app/repositories/knowledge_item.py` | `distinct_active_repo_count`, `transfer_repo_links_bulk`, `add_repo_links` | 1, 2 |
| `backend/app/reposcanv2/stages/feature_merge.py` | drop `is_workspace` plumbing | 1 |
| `backend/app/mcp/handlers_knowledge.py` | `handle_apply_feature_merge_plan` | 2 |
| `backend/app/mcp/server.py` | register new MCP tool | 2 |
| `backend/app/mcp/synth_feature_writer.py` | id-based audit stamping | 2 |
| `backend/app/config.py` | model + budget config | 3 |
| `backend/app/services/scan_pipeline.py` | two-section `build_merge_prompt` | 3 |
| `backend/app/services/feature_clusterer.py` | NEW — embedding ANN + union-find | 4 |
| ~~`backend/app/scan/global_/contract_pre_link.py`~~ | DROPPED with Phase 5 | — |
| `backend/tests/scan/test_feature_merge.py` | scenarios across phases 1–4 | 1–4 |

## Reused, unchanged

`embed_missing_items`, `dedup_merged_features`, `mark_canonical_for_active_kis`, `mark_unvisited_for_inactive_kis`, `MergeOutcome` enum, `KnowledgeRepoLink` model, pgvector cosine pattern (already used in `services/bug_linker.py` at threshold 0.40 — merge uses 0.75 for stricter precision).

## Per-phase code review (memory enforced)

Every phase ends with the same checklist:

1. **Lint zero** — `ruff check .` and `mypy app/` clean. No "pre-existing" dismissals (memory: `feedback_lint_zero`).
2. **No big files** — every file touched in the phase < 200 lines. Split helpers eagerly (memory: `feedback_code_principles`).
3. **No hack / no hardcode** — every magic number lifted to config; thresholds env-tunable. Same memory.
4. **Modular & reusable** — new code lives in services/repositories, not inlined in handlers. Same memory.
5. **GitNexus impact discipline** —
   - Before edits in the phase: `gitnexus_impact` on every symbol being modified; report HIGH/CRITICAL to user before proceeding (CLAUDE.md rule).
   - Before commit: `gitnexus_detect_changes()` to confirm scope (CLAUDE.md rule).
6. **No `Co-Authored-By: Claude`** trailer in commits (memory: `feedback_no_claude_coauthor`).
7. **Conda env** — any ad-hoc Python tooling runs under `conda activate python3129` (memory: `feedback_conda_env`).
8. **User review pause** — assistant stops after gate passes; waits for explicit "go" before next phase (memory: `feedback_engine_phases` pattern).

## Verification (end-to-end after Phase 3)

1. **Single repo** — add one repo, scan; expect `feature_merge` step shows `kept == input`, `dropped == 0`. SQL: `synthesized_features.merge_outcome` all CANONICAL; `knowledge_items` count matches synthesis.
2. **New repo added later** — second repo, scan only it; expect `distinct_active_repo_count == 2` triggers merge; cross-repo dupe → single KI with two `KnowledgeRepoLink` rows; absorbed KI `is_active=FALSE` → cleanup-deleted.
3. **Structured-op contract** — fixture `{ops:[…]}` covers merge/create/link; cross-org `canonical_id` rolls back the whole txn.
4. **>16K hybrid path** — seed 16001 features, 200 cosine-similar pairs across 2 repos; assert clusters formed and Claude called once per cluster.
5. **Manual UI smoke** — `npm run dev`; trigger via Settings → Code; watch scan timeline chips render correct counts.
6. **GitNexus index refresh** — `npx gitnexus analyze` after Phase 5 commit (CLAUDE.md hook does this on commit, but verify).

## Out of scope (deliberate)

- Concurrent scans across same org — keep per-org single-scan lock (user choice).
- Embedding pre-link inside synthesis — user picked LLM-merge-only (Q4).
- UI for human-in-the-loop merge approval — defer until merge noise complaints surface.
- Confidence scoring on merge outcomes — binary CANONICAL/MERGED_INTO is enough now.

## Brainstorm outcome — fully GitNexus-monolithic considered, rejected

Verified against [GitNexus ARCHITECTURE.md](https://github.com/abhigyanpatwari/GitNexus/blob/main/ARCHITECTURE.md): groups bridge per-repo graphs via the Contract Bridge, they don't fuse them. Three architectural facts:

1. **Communities are per-repo** (Leiden runs independently on each member). No cross-repo feature emerges from community detection alone.
2. **Contract Bridge is exact-match HTTP/topic only** — invisible for any feature pair without a declared contract.
3. **Community labels are technical** (`auth_handler_module`); user-facing names ("Authentication") are an LLM job, by design.

So `group_sync` is a useful **pre-link**, not a replacement → captured as Phase 5 (optional, flagged). LLM merge phase stays for the structurally-disconnected long tail. No open GitHub issues block this design (issue tracker checked 2026-04-27).

Sources used: [Anthropic — Context windows](https://platform.claude.com/docs/en/build-with-claude/context-windows), [Anthropic — What's new in Claude Opus 4.7](https://platform.claude.com/docs/en/about-claude/models/whats-new-claude-4-7), [GitNexus ARCHITECTURE.md](https://github.com/abhigyanpatwari/GitNexus/blob/main/ARCHITECTURE.md), [Entity Resolution at Scale (Graph Praxis)](https://medium.com/graph-praxis/entity-resolution-at-scale-deduplication-strategies-for-knowledge-graph-construction-7499a60a97c3), [LLM-empowered KG construction (arXiv:2510.20345)](https://arxiv.org/html/2510.20345v1).
