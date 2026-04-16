# Phase 9: Learning & Skill Growth — Research Notes

## Status
Planning paused — multi-assignment via task splitting is a prerequisite.
Full implementation plan (v4): `.claude/plans/indexed-roaming-blanket.md`

---

## What Exists (~80% foundation)

| Component | File | Status |
|-----------|------|--------|
| FeatureLearning model | `backend/app/models/feature_learning.py` | Fields: cycle_time_days, estimated_days, bug_count, retrospective_md (never populated), embedding (never populated) |
| SkillProfile model | `backend/app/models/skill_profile.py` | Per-dev per-module: skill_score (0-1.0), touch_count, last_touch |
| Git skill analyzer | `backend/app/services/git_analyzer.py` | score = min(touch_count/50, 1.0) x recency_weight |
| Smart assignment | `backend/app/services/smart_assignment.py` | skill(50%) + workload(30%) + recency(20%), LLM tiebreak |
| Bus factor detection | `backend/app/services/tree_skill_analysis.py` | Flags single-developer modules |
| Estimation engine | `backend/app/services/estimation_engine.py` | PERT 3-point + Monte Carlo (10K samples) |
| Estimation context | `backend/app/services/estimation_context.py` | Backlog depth, assignee skill, last 5 completed BUDs |
| LLM estimation | `backend/app/services/estimation_llm.py` | Claude generates O/M/P per phase |
| Feature lifecycle | `backend/app/services/feature_lifecycle.py` | `_record_feature_learning()` on BUD closure |
| Skills UI | `frontend/src/views/skills/SkillProfilesView.vue` | Developer/module grouping, bus factor warnings |

## What's Missing (~20%)

### 1. Developer Velocity Factor
Per-developer, per-phase-type calibration: `avg(actual_days / estimated_days)` from FeatureLearning history.

**Why per-phase:** BUD phases are handled by different roles (PM → Designer → Tech Lead → Developer → QA). Velocity of "Developer A in development phases" is different from "QA B in testing phases."

**Team average fallback:** For new devs with < 3 completed BUDs, use org-wide average.

**Feed into estimation:** Upgrade `get_historical_context()` to include:
```
Developer calibration:
- Developer A's development phases: avg overrun +25% (8 completed)
- QA not yet assigned (org average: +5%)
Org-wide phase calibration:
- Development: avg overrun +18%
- Code review: avg overrun +35% (bottleneck)
```

### 2. Enriched FeatureLearning Data Capture
`_record_feature_learning()` only captures 3 fields — throws away rich data available at closure time.

**New fields needed:**
- `original_estimated_days` — from first BUDEstimateSnapshot (trigger="prd_completed")
- `final_estimated_days` — from latest snapshot
- `estimation_revision_count` — scope creep signal
- `complexity` — complexity score at closure
- `assignee_id` — who delivered (but see Blocker below)
- `phase_metrics` (JSONB) — per-phase actual vs estimated with assignee per phase

**`phase_metrics` structure:**
```json
{
  "phases": {
    "development": {
      "estimated_days": 12.0,
      "actual_days": 18.5,
      "assignee_id": "uuid",
      "assignee_name": "Developer A",
      "entered_at": "2026-04-04T14:30:00Z",
      "exited_at": "2026-04-23T09:00:00Z"
    }
  },
  "bottleneck_phase": "development",
  "approval_wait_hours": 14.2,
  "pr_merge_hours_avg": 6.5,
  "pr_count": 3,
  "bugs_during_dev": 2,
  "bugs_during_testing": 5,
  "bugs_critical": 1,
  "agent_task_count": 4,
  "agent_total_minutes": 28.3,
  "estimate_drift_pct": 15.0
}
```

### 3. Retrospective Generation
LLM-generated analysis of full BUD lifecycle using phase_metrics.

**What the retrospective covers:**

| Metric | Source | Reveals |
|--------|--------|---------|
| Per-phase estimated vs actual | BUDTimelineEvent (status_change) + BUDEstimateSnapshot | Where time was lost/saved |
| Bottleneck phase | Largest overrun | Focus area for improvement |
| Approval wait hours | Timeline: requested → approved events | Process delay |
| PR merge time | PullRequest: merged_at - created_at | Code review throughput |
| Bugs during dev | Bug model (bug_type != PRODUCTION) | Rework cost |
| Bugs during testing | Bug model (bug_type == TESTING) | Quality escapes |
| Critical bugs | Bug model (severity == CRITICAL) | Severity |
| Agent execution time | BUDAgentTask (completed tasks) | AI overhead |
| Estimate drift | First vs final BUDEstimateSnapshot | Scope creep |
| Developer velocity | Historical actual/estimated ratio | Personal calibration |

**Implementation:** Background task via `asyncio.create_task()` (same pattern as `bud_closure.py:_trigger_impacted_repo_scan`). 1-turn `run_claude_code()` with max_turns=1, timeout=120s. Non-fatal.

### 4. Bus Factor Alerting
Add Phase E1a to scan pipeline (after skill analysis, before design extract). Detect single-dev modules, notify org admins. Piggybacks on BUD-closure scan — no daily scheduler needed.

### 5. Learning Insights UI
Frontend view at `/learning` with: velocity overview, estimation accuracy trends, retrospectives, bus factor alerts.

---

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| **Drop vector search for estimation** | Features never match semantically. Structured data (complexity, phase type, developer speed) is more predictive |
| **Drop FeatureLearning embedding** | No vector search = no need for embeddings |
| **Drop daily skill rebuild** | BUD-closure scan already runs Phase E (git skill analysis) |
| **Per-phase per-developer velocity** | Estimation is per-phase (PERT per phase). Different roles handle different phases. More granular = more useful |
| **Team avg for new devs** | COCOMO II precedent: use calibration factors with fallback |
| **asyncio.create_task for retro** | Fire-and-forget side effect, not user-initiated. Job queue is for user-facing work |
| **Bus factor in scan pipeline** | Phase E1a fits naming convention, runs after skills are fresh, independent failure |

---

## Research Sources

### AI & Developer Productivity
- **METR 2025 Study** ([arxiv.org/abs/2507.09089](https://arxiv.org/abs/2507.09089)): AI slowed experienced open-source devs by 19%, but devs estimated they were 20% FASTER. Huge perception gap.
- **DX Q1 2026 Report** ([newsletter.getdx.com](https://newsletter.getdx.com/p/ai-assisted-engineering-q1-2026-impact)): Junior engineers saving 4.9 hrs/week vs staff+ saving 4.8 hrs. AI levels the playing field.
- **Google RCT**: Developers using AI completed tasks ~21% faster (96 min vs 114 min).
- **AI Productivity Paradox**: Individual output up (21% more tasks, 98% more PRs merged), but organizational delivery metrics stay flat.

### Estimation & Velocity
- **COCOMO II** ([greenbay.usc.edu](https://greenbay.usc.edu/csci577/tools/cocomo/Help/Model/model3.htm)): Effort multipliers (EM) adjust estimates by developer capability. Precedent for per-developer calibration factors.
- **DORA Metrics** ([dora.dev](https://dora.dev/guides/dora-metrics/)): Don't use individual metrics for performance evaluation. But using them for estimation calibration is different — accuracy, not judgment.
- **Scrum.org** ([scrum.org](https://www.scrum.org/resources/blog/bye-bye-velocity-hello-throughput)): Industry moved from individual velocity to team throughput. Individual velocity "fell into disrepute" for evaluation but remains valid for self-calibration.
- **Sprint Velocity Research**: Structured velocity tracking improves estimation accuracy by ~40% (Journal of Software Engineering, 2021).

### Feedback Loops
- **Martin Fowler's Feedback Flywheel** ([martinfowler.com](https://martinfowler.com/articles/reduce-friction-ai/feedback-flywheel.html)): "Each rotation of the loop leaves the infrastructure a little better prepared for the next." The loop: BUD closes → record actual vs estimated → compute velocity → next estimate uses it → repeat.
- **Fowler's Learning Loop** ([martinfowler.com](https://martinfowler.com/articles/llm-learning-loop.html)): When a developer fixes an issue and adds an observation to a learning log, the next developer benefits without knowing the exchange happened.

---

## Blocker: Multi-Assignment

**Problem:** `bud_documents.assignee_id` is a single FK. Only one person assigned per phase. But big features need:
- 2+ developers in DEVELOPMENT (frontend + backend)
- 2+ QA in TESTING

**Current multi-dev tracking:** Contributors tracked via DevActivityLog commits + PullRequest authors at closure (for XP awards). But assignee-per-phase is single.

**Impact on Phase 9:** Per-phase velocity factor needs to know WHO worked on each phase. With single assignee, we only track the "primary" developer, missing contributor velocity data.

**Proposed solution:** Split AI-generated tech plan into discrete tasks. Developers self-assign to tasks within a phase. This enables multi-assignment AND better velocity tracking.

**Must solve multi-assignment FIRST before Phase 9 velocity tracking makes sense.**

---

## Implementation Plan Summary (v4)

| Sub-Phase | What | New Files | Modified Files |
|-----------|------|-----------|----------------|
| A | Enrich FeatureLearning data capture | 1 migration, 1 repo | 2 (model, feature_lifecycle) |
| B | Developer velocity factor + estimation context | 1 service | 2 (estimation_context, bud_estimation) |
| C | Retrospective generation | 1 service | 1 (feature_lifecycle trigger) |
| D | Bus factor alerting | 1 migration | 3 (notification model/service, scan_pipeline) |
| E | API endpoints | 0 | 2 (skills.py, schemas) |
| F | Frontend Learning Insights | 2 (store, view) | 3 (types, router, sidebar) |

**Total: 7 new files, 10 modified files. A+B parallel with D. C after A. E after A+B. F after E.**
