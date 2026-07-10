# TaskFlow — Sample Repositories for Scan Testing

Sample repos that exercise the scan pipeline's cross-repo feature detection, skill profiling, code location tracking — plus an end-to-end test suite that drives the UI of the running app, and a standalone Java/Spring Boot sample.

## Repos

| Repo | Type | Port | Modules |
|------|------|------|---------|
| `taskflow-api` | FastAPI backend | 9001 | auth, tasks, notifications, billing |
| `taskflow-worker` | Python background jobs | — | auth, notifications, reminders, billing |
| `taskflow-web` | Vue 3 frontend | 9002 | auth, tasks, notifications, billing |
| `taskflow-qa` | Playwright + Cucumber BDD e2e suite | — | drives `taskflow-web` at 9002 via `taskflow-api` at 9001 |
| `taskflow-spring` | **Java / Spring Boot 3 backend** | 9003 | auth, tasks, notifications, billing |

The repos are **hosted on GitHub, not committed into bodhiorchard** — they're
gitignored here so FT-testing PR merges don't show up as bodhiorchard-side
changes. `taskflow-spring` lives in its own public repo:
**https://github.com/mickyarun/taskflow-java-bodhiorchard-demo**

## Setup Git History

The sample repos need git commit history with different authors for skill
profile testing. The setup script clones each repo (into `examples/`) and, for
the Python/Vue ones, rebuilds a 4-author history:

```bash
cd examples
bash setup-git-history.sh
```

This produces git repos with 4 authors (Alice, Bob, Carol, Dave) and ~6 commits
each. `taskflow-spring` is cloned from its GitHub repo with its history already
baked in.

### Clone just the Java sample

To test the Java scan on its own, clone it directly (use `git clone`, **not**
"Download ZIP" — a ZIP has no `.git`, so branch detection and skill profiles
won't work):

```bash
git clone https://github.com/mickyarun/taskflow-java-bodhiorchard-demo.git
```

Then add the cloned folder's absolute path in Bodhiorchard **Settings →
Repositories** (or the setup wizard's **Local path** tab), branch `main`, and
run a scan. Expect ~4 features (Authentication, Task Management, Notifications,
Billing), `NotificationService` as a cross-feature hub, and 4 skill profiles.

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

# 4. QA suite (optional — once 9001/9002 are up)
cd examples/taskflow-qa
npm install
npm test                # Playwright + Cucumber against the running web app

# 5. Java / Spring Boot sample (optional — JDK 17 + Maven; runs standalone)
cd examples/taskflow-spring
mvn -DskipTests package
java -jar target/taskflow-spring-1.0.0.jar   # → http://localhost:9003
```

> Running the apps is optional — a scan only reads source. Build/run is only
> needed to hit the live endpoints. See each repo's own README for details.

## Testing the Scan Pipeline

1. Start Bodhiorchard (`uvicorn` on default port 8000)
2. In Settings > Repositories, add the 3 source repos (the QA suite isn't a scan target):
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
