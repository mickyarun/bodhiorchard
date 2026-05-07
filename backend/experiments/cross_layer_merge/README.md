# Cross-Layer Merge — Experimental Sandbox

Iterate the cross-layer feature-merge logic in isolation against a small, hand-curated dataset before promoting it into the main scan pipeline.

See plan: `~/.claude/plans/summary-written-to-plan-compiled-sun.md`.

## Why a sandbox

The full scan pipeline (clone → GitNexus index → extract → synthesize → merge) takes hours per iteration. The sandbox skips everything except merge, so prompt tweaks and verifier-logic changes have a 2–5 minute feedback loop instead of a multi-hour one.

## Layout

```
schema/      — SQLAlchemy models for xlm_* tables (mirror real schema)
seed/        — hand-curated seed_data.json + loader (creates xlm_* tables, truncates, inserts)
classify/    — repo classifier (frontend / backend / processor / db)
pair/        — pair planner + per-pair Claude verifier
prompts/     — verifier prompt templates
apply/       — sandbox merge applier (mirrors apply_feature_merge_plan semantics)
report/      — before/after stats
tests/       — unit + integration tests
run.py       — CLI entry: load | classify | pair | verify | reset | report
```

## Usage

From `backend/`:

```bash
# One-time: edit seed/seed_data.json with representative repos + KIs + synth rows.

.venv/bin/python -m experiments.cross_layer_merge.run load       # create tables, load seed
.venv/bin/python -m experiments.cross_layer_merge.run classify   # populate repo_layer/tech/db
.venv/bin/python -m experiments.cross_layer_merge.run pair       # emit pair plan
.venv/bin/python -m experiments.cross_layer_merge.run verify     # run Claude per pair, apply merges
.venv/bin/python -m experiments.cross_layer_merge.run report     # show before/after diff

# Iterate:
vim experiments/cross_layer_merge/prompts/verify_pair.py
.venv/bin/python -m experiments.cross_layer_merge.run reset && \
  .venv/bin/python -m experiments.cross_layer_merge.run verify
```

## Promotion to main pipeline

When sandbox results are clean (Magic Link, Open Banking, Card Payments, Payment Links each consolidate to 1 KI on seed data with no false merges on control rows), the proven code moves to:

- `classify/mode_detection.py` → `app/services/scan/stages/mode_detection.py`
- `pair/planner.py`, `pair/verifier.py`, `prompts/verify_pair.py` → `app/scan/cross_layer/`
- `apply/merge_applier.py` is discarded — production uses the existing `apply_feature_merge_plan` MCP handler.

The `xlm_*` tables and `seed_data.json` stay here as a regression test bench.

## Isolation notes

- Uses its own SQLAlchemy `DeclarativeBase` (`XLMBase`) so Alembic autogenerate doesn't see the tables.
- All tables prefixed `xlm_` — drop trivially with `DROP TABLE xlm_*` if needed.
- Reuses `app.database.engine` so pgvector and async-session pooling work unchanged.
