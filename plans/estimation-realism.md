# Estimation realism — gates, complexity, and progress

## Context

The capacity-divisor rework removed the 10× floor that pushed every estimate to ~2 months
(active-BUD horizon dropped from avg 69 → 33 business days after a re-estimate sweep). Two
canary BUDs then exposed three residual distortions, addressed here as three independent,
separately-shippable changes (backend-only, no migrations):

- **BUD-020** (in UAT): the UAT phase alone was budgeted ~20 business days — a sign-off gate
  run through `effort ÷ capacity` (LLM 4.3 effort-days ÷ 0.21 reviewer capacity).
- **BUD-050** (395-char spec, 0 QA): scored complexity 3 only because it touches 4 repos
  (`impacted_repos ≥ 4` adds +2.0 additively, independent of real scope).
- **BUD-050**: development todos 8/8 complete, yet still "completes Jul 3" — the estimator is
  status-driven and re-budgets the whole current phase, ignoring completed work.

## Decisions

- Shipped as three separate changes, in impact order (gates → complexity → progress).
- `code_review` is treated as a review gate (with `bud`, `uat`).
- Progress signal combines completed todos with merged PRs.
- No lifecycle auto-transition; no schema migration (`bud_todos.phase` already exists;
  phase classification is a constant map, not a DB column).

## Engineering standards

Every change follows the repo bars: code review after each meaningful step
(`pr-review-toolkit:code-reviewer`, plus `silent-failure-hunter` on any fallback/discount
path); no hardcoded tunables (named module constants only); files ≤ ~200 lines, single
concern; imports at file top; SQL only in repository classes; `mypy --strict` and `ruff`
clean under `conda activate python3129`; `pytest` only; DCO sign-off with the personal
identity and no auto-generated co-author trailer; descriptive commit/PR wording with no
customer-specific names.

## Review-gate phases

Classify each phase as build (hands-on) or gate (review/sign-off). Build phases keep
`effort ÷ capacity`. Gate phases get a small **capped turnaround budget** —
`base + penalty · reviewer_backlog`, capped — turned into a narrow PERT triple and fed to
the existing pure Monte Carlo engine with a capacity divisor of 1.0, so the engine keeps no
phase-kind knowledge. Touchpoints: `phase_roles.py` (`PHASE_KIND`, `is_gate_phase`),
`estimation_gates.py` (new turnaround model), `bud_estimation.py` (orchestrator override +
audit fields). The discarded LLM gate effort and the chosen turnaround are both persisted in
the estimate snapshot for explainability.

## Complexity scoring

Make the repo-count contribution in `estimation_heuristics.compute_complexity` proportional
to a content/QA scope signal instead of a flat additive, so a tiny spec across many repos
stays low while a large multi-repo change still scores high. Soften the LLM anchor in
`estimation_llm` / `estimation_prompt_format` so the model rates complexity independently,
clamped within ±1 of the heuristic as a sanity bound.

## Progress-aware current phase

Discount the current phase by work already completed, without forcing a status change. New
repository methods expose per-phase todo counts (via `bud_todos.phase`) and a
merged-PR-on-current-phase signal; `estimation_context.current_phase_progress` combines them
into a ratio; `bud_estimation` scales only the current phase's PERT triple by `(1 − ratio)`,
floored at a small handoff residual. Downstream phases are untouched.

## Verification (each change)

1. `conda activate python3129`; `ruff check --fix && ruff format`; `mypy app/` strict (zero);
   `pytest tests/services/ -k "capacity or estimation or bud_estimation or phase_roles or gates"`.
2. Final code-review pass before opening the PR.
3. Post-deploy: re-run the one-off re-estimate sweep, then spot-check canaries via prod psql
   (BUD numbers only): BUD-020 UAT wall-clock drops from ~20 days to a few; BUD-050 complexity
   ≤ 2 and its completed development phase collapses toward the residual.
