# TaskFlow — Sample Repositories for Scan Testing

Three sample repos that exercise the scan pipeline's cross-repo feature detection, skill profiling, and code location tracking.

## Repos

| Repo | Type | Port | Modules |
|------|------|------|---------|
| `taskflow-api` | FastAPI backend | 9001 | auth, tasks, notifications, billing |
| `taskflow-worker` | Python background jobs | — | auth, notifications, reminders, billing |
| `taskflow-web` | Vue 3 frontend | 9002 | auth, tasks, notifications, billing |

## Setup Git History

The sample repos need git commit history with different authors for skill profile testing. Run the setup script first:

```bash
cd examples
bash setup-git-history.sh
```

This creates proper git repos with 4 authors and ~6 commits each.

## Quick Start

```bash
# 1. API
cd examples/taskflow-api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m src.create_db
uvicorn src.main:app --reload --port 9001

# 2. Worker (separate terminal)
cd examples/taskflow-worker
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m src.main

# 3. Frontend (separate terminal)
cd examples/taskflow-web
npm install
npm run dev -- --port 9002
```

## Testing the Scan Pipeline

1. Start FlowDev (`uvicorn` on default port 8000)
2. In Settings > Repositories, add all 3 repos:
   - `/path/to/examples/taskflow-api`
   - `/path/to/examples/taskflow-worker`
   - `/path/to/examples/taskflow-web`
3. Map branches (main/main for all)
4. Click **Full Rescan**

### What to Verify

| Check | Expected |
|-------|----------|
| Features extracted | ~4-6 cross-repo features (Auth, Tasks, Notifications, Billing, Reminders) |
| Feature grouping | All notification code = 1 "Notifications" feature, not 3 separate ones |
| Repo links | Each feature linked to correct repos via `knowledge_to_repo` |
| code_locations per repo | Junction table has different paths per repo for same feature |
| Skill profiles | 4 authors with feature_id populated |
| Embeddings | Zero NULL embeddings on active features |

### SQL Verification Queries

```sql
-- Features with repo links
SELECT ki.title, tr.name as repo
FROM knowledge_items ki
JOIN knowledge_to_repo ktr ON ki.id = ktr.knowledge_id
JOIN tracked_repositories tr ON ktr.repo_id = tr.id
WHERE ki.is_active AND ki.category = 'feature_registry'
ORDER BY ki.title;

-- Per-repo code_locations on junction table
SELECT ki.title, tr.name, ktr.code_locations
FROM knowledge_to_repo ktr
JOIN knowledge_items ki ON ktr.knowledge_id = ki.id
JOIN tracked_repositories tr ON ktr.repo_id = tr.id
WHERE ki.is_active;

-- Skill profiles with feature links
SELECT u.name, sp.module, sp.skill_score, sp.touch_count, ki.title as feature
FROM skill_profiles sp
JOIN users u ON sp.user_id = u.id
LEFT JOIN knowledge_items ki ON sp.feature_id = ki.id;

-- Orphan check (should be 0)
SELECT count(*) FROM knowledge_items ki
LEFT JOIN knowledge_to_repo ktr ON ki.id = ktr.knowledge_id
WHERE ktr.id IS NULL AND ki.is_active AND ki.category = 'feature_registry';

-- Embedding check (should be 0)
SELECT count(*) FROM knowledge_items
WHERE embedding IS NULL AND is_active AND category = 'feature_registry';
```

## Authors & Expertise

| Author | Email | Specialty | Repos |
|--------|-------|-----------|-------|
| Alice Kim | alice@taskflow.dev | Authentication, security | api, worker |
| Bob Martinez | bob@taskflow.dev | Frontend, task management | api, web |
| Carol Singh | carol@taskflow.dev | Billing, payments | api, worker, web |
| Dave Chen | dave@taskflow.dev | Fullstack, notifications | all 3 |

## Cross-Repo Feature Map

| Feature | taskflow-api | taskflow-worker | taskflow-web |
|---------|-------------|-----------------|--------------|
| Authentication | `src/auth/` | `src/auth/` | `src/views/auth/` |
| Task Management | `src/tasks/` | `src/reminders/` | `src/views/tasks/` |
| Notifications | `src/notifications/` | `src/notifications/` | `src/components/notifications/` |
| Billing | `src/billing/` | `src/billing/` | `src/views/billing/` |
