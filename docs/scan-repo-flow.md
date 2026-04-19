# Scan Repository Flow

> Current-state documentation for the scan pipeline. Written for future optimization work.

---

## Entry Points

There are **two ways** a scan gets triggered:

| Entry point | Endpoint | File |
|-------------|----------|------|
| **Settings UI** (manual) | `POST /v1/skills/scan` | `backend/app/api/v1/skills.py:35` |
| **Setup Wizard** (auto) | `POST /setup/initialize` | `backend/app/api/v1/setup.py:142` |

Both ultimately call the same function: `run_scan_pipeline()` in `backend/app/services/scan_pipeline.py:189`.

---

## Pre-scan Validation (`skills.py:40–123`)

Before dispatching, the API handler performs these gates in order:

1. **Embedding service health** — `embedding_service.check()` must succeed
2. **Active repos** — fetches all ACTIVE rows from `tracked_repositories`
3. **Branch mapping** — every repo must have both `main_branch` and `develop_branch` set
4. **Disk check** — each repo path must exist and contain a `.git` directory; missing repos are skipped with a warning
5. **At least one valid repo** required, else HTTP 400

On success, creates an in-memory `ScanStatus`, dispatches `run_scan_pipeline` via FastAPI `BackgroundTasks`, and returns a `scanId` for polling.

---

## Single Repo vs Multiple Repo

The pipeline handles both modes with a single code path. The flag is:

```python
is_workspace = len(repo_paths) > 1  # scan_pipeline.py:225
```

### What stays the same

- Same API endpoint, same `run_scan_pipeline` function
- Same per-repo phases (A → B → B1 → D → E → E1b)
- Same global phases (B2 → E2 → B3 → F → G)
- Same status polling mechanism

### What differs

| Aspect | Single repo | Multi-repo (workspace) |
|--------|-------------|------------------------|
| Per-repo loop | Runs once | Runs sequentially for each repo |
| Progress calc | Full 80% range for one repo | 80% divided equally among repos |
| Phase B2 synthesis | Single repo's clusters | All repos' clusters combined |
| Phase B3 merge | Embedding only | **Cross-repo semantic dedup** — merges duplicate features found in different repos |
| SHA storage | Single entry in `repo_shas` | Per-repo entries in `repo_shas` dict |

---

## Pipeline Phases (detailed)

### Per-repo phases (run inside `for repo_path in repo_paths` loop)

#### Phase A — Scan mode detection (`scan_phases.py`)
- Determines **incremental vs full** rescan
- Checks last scanned SHA (from `tracked_repo.head_sha` → fallback to `org.config.knowledge.repo_shas`)
- If >30% of files changed since last SHA → forces full rescan
- Outputs: `is_incremental`, `deleted_files` list

#### Phase B — GitNexus indexing (`scan_pipeline.py:327`)
- Runs `index_repo_with_gitnexus(repo_path, force=not is_incremental)`
- Produces code **clusters** (groups of related files/symbols)
- On success, ensures GitNexus MCP server is initialized

#### Phase B1 — Repo setup (`scan_phases.py`)
- Creates worktrees, initializes MCP config, sets up hooks
- Configures `.gitignore` for generated files
- Optionally creates a commit + push + PR for repo scaffolding

#### Phase D — Stale cleanup (incremental only) (`scan_pipeline.py:389`)
- Only runs if `is_incremental and deleted_files`
- Calls `cleanup_stale_references(db, org_id, deleted_files)`
- Removes knowledge items referencing files that no longer exist

#### Phase E — Git skill analysis (`scan_pipeline.py:399`)
- Runs `analyze_repo_skills(repo_path, feature_map)`
- Analyzes git commit history per author per code module
- Produces skill profiles (who knows what)
- Maps git emails to platform users via `email_to_user`

#### Phase E1b — Design system extraction (`scan_pipeline.py:422`)
- Conditional: only if design-related files are detected in the repo
- Auto-extracts design tokens, component patterns
- First repo with a design system becomes the org default

#### Post-loop: stash + restore
- Before scanning, the pipeline stashes uncommitted work and checks out `main_branch`
- After scanning, it restores the original branch and pops the stash

---

### Global phases (run once after all repos)

#### Phase B2 — Feature synthesis (`scan_pipeline.py:448`)
- Uses Claude Code CLI to convert raw clusters into human-readable **business features**
- Clusters from ALL repos are queued together via `set_synthesis_queue()`
- `phase_b2_synthesis()` processes them, receiving `is_workspace` flag
- Produces `knowledge_items` with category `feature_registry`

#### Phase E2 — Skill remap (`scan_pipeline.py:461`)
- Re-runs skill analysis using synthesized features as module names
- Only runs if synthesis produced features (`total_features_synthesized > 0`)
- Updates skill profiles to reference feature-based modules instead of raw file paths

#### Phase B3 — Cross-repo merge + embedding (`scan_pipeline.py:475`)
- **Single repo:** generates embeddings for items missing them
- **Multi-repo (workspace):** additionally performs **semantic deduplication** — finds features in different repos that describe the same concept and merges them into a canonical item
- Updates org config with merged results

#### Phase G — Persist (`scan_pipeline.py:491`)
- Saves `head_sha` per repo to `repo_shas` in org config
- Updates `tracked_repositories` rows with new SHAs and counts
- Records overall scan mode, profile count, unmatched emails

---

## Status Tracking & Polling

### Backend

Status is tracked in an **in-memory dict** (not the database):

```python
scan_statuses: dict[str, ScanStatus] = {}  # skills.py
```

`ScanStatus` fields updated during the pipeline:

| Field | Example values |
|-------|---------------|
| `status` | `started` → `analyzing_changes` → `indexing` → `analyzing_skills` → `cleaning_stale` → `completed` / `failed` |
| `progress_pct` | 0 → 100 |
| `features_indexed` | count of synthesized features |
| `profiles_found` | count of skill profiles |
| `stale_cleaned` | count of removed stale items |

### Frontend polling

```
GET /v1/skills/scan/{scan_id}/status  (every 1 second)
```

`SettingsRepositories.vue` polls via `startPolling()` at line 814, updates a progress bar and status label, and stops on `completed` or `failed`.

---

## Data Produced

| Output | Table / Storage | Source phase |
|--------|-----------------|-------------|
| Code clusters → features | `knowledge_items` (category=`feature_registry`, source=`scan`) | B + B2 |
| Skill profiles | `skill_profiles` | E + E2 |
| Embeddings | `knowledge_items.embedding` (pgvector, 384d) | B3 / F |
| Design system refs | `design_system_refs` | E1b |
| Repo head SHAs | `tracked_repositories.head_sha` + `org.config.knowledge.repo_shas` | G |
| Scan timestamp | `tracked_repositories.last_scanned_at` | G |

---

## Key Files

| Layer | File | Role |
|-------|------|------|
| API trigger | `backend/app/api/v1/skills.py` | Validation, dispatch, status endpoint |
| API (setup) | `backend/app/api/v1/setup.py` | Auto-trigger during org init |
| Orchestrator | `backend/app/services/scan_pipeline.py` | `run_scan_pipeline()` — main loop and global phases |
| Phase impls | `backend/app/services/scan_phases.py` | Individual phase logic (A, B1, D, E, E2, G) |
| Helpers | `backend/app/services/scan_helpers.py` | Timing, embedding, dedup utilities |
| GitNexus indexer | `backend/app/services/gitnexus_indexer.py` | Phase B — code clustering |
| Git analyzer | `backend/app/services/git_analyzer.py` | Phase E — commit history analysis |
| Schemas | `backend/app/schemas/skills.py` | `ScanRequest`, `ScanResponse`, `ScanStatus` |
| Frontend UI | `frontend/src/views/settings/SettingsRepositories.vue` | Scan buttons, progress, polling |
| Setup store | `frontend/src/stores/setup.ts` | Auto-scan after org creation |
| Settings store | `frontend/src/stores/settings.ts` | Repo CRUD operations |

---

## Flow Diagram

```
┌─────────────────────────────────────────────────────────┐
│  User clicks "Scan" / "Full Rescan" in Settings UI      │
│  OR setup wizard auto-triggers after org creation        │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  POST /v1/skills/scan { fullRescan: bool }              │
│  ─────────────────────────────────────                  │
│  1. Check embedding service health                      │
│  2. Load active repos from tracked_repositories         │
│  3. Validate branch mappings                            │
│  4. Validate paths exist on disk                        │
│  5. Create ScanStatus(scanId, "started", 0%)            │
│  6. Dispatch background task → run_scan_pipeline()      │
│  7. Return { scanId } immediately                       │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  run_scan_pipeline() [BACKGROUND]                       │
│  ═══════════════════════════════════                    │
│                                                         │
│  is_workspace = len(repo_paths) > 1                     │
│                                                         │
│  FOR EACH repo (sequential):                            │
│  ┌────────────────────────────────────────────┐         │
│  │  stash + checkout main_branch              │         │
│  │  Phase A:  Scan mode (incremental/full)    │         │
│  │  Phase B:  GitNexus indexing → clusters     │         │
│  │  Phase B1: Repo setup (worktrees, hooks)   │         │
│  │  Phase D:  Stale cleanup (if incremental)  │         │
│  │  Phase E:  Git skill analysis              │         │
│  │  Phase E1b: Design system extraction       │         │
│  │  Record HEAD SHA                           │         │
│  │  restore original branch + pop stash       │         │
│  └────────────────────────────────────────────┘         │
│                                                         │
│  GLOBAL (once, all repos):                              │
│  ┌────────────────────────────────────────────┐         │
│  │  Phase B2: Feature synthesis (Claude Code) │         │
│  │  Phase E2: Skill remap with features       │         │
│  │  Phase B3: Cross-repo merge + embedding    │         │
│  │  Phase G:  Persist SHAs, config, counts    │         │
│  └────────────────────────────────────────────┘         │
│                                                         │
│  ScanStatus → "completed" / "failed"                    │
│  Send notification via WebSocket                        │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Frontend polls GET /v1/skills/scan/{id}/status (1s)    │
│  Updates progress bar, status label, feature counts     │
│  Stops polling on "completed" or "failed"               │
└─────────────────────────────────────────────────────────┘
```

---

## Known Areas for Optimization

> These are observations, not changes. To be addressed in a follow-up.

1. **Sequential per-repo scanning** — repos are scanned one at a time; parallelizing independent phases could reduce wall time for workspaces
2. **In-memory status tracking** — `scan_statuses` dict is lost on server restart; a scan started before a restart becomes untrackable
3. **Stash/checkout dance** — each repo is stashed and switched to `main_branch` for scanning, then restored; this could conflict with user activity
4. **No resume/retry** — if the pipeline fails mid-way, the entire scan must be restarted from scratch
5. **1-second polling** — frontend polls every second regardless of scan duration; could use WebSocket events or exponential backoff
6. **Phase B2 synthesis** — uses Claude Code CLI subprocess; timeout and error handling could be tightened
7. **Full rescan deletes all features** — `delete_by_category_excluding_source` wipes scan-sourced features before re-indexing; no rollback if the new scan fails partway
