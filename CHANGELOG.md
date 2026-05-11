# Changelog

All notable changes to Bodhiorchard will be documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-05-11

First public release. Bodhiorchard™ ships as an open-source, local-first AI dev-ops platform under Apache 2.0.

### Added

- **BUD (Business Understanding Document) lifecycle** — markdown-first specs that flow `bud → design → development → testing → uat → prod → closed`, numbered per organization.
- **11 AI agents** — Triage, BUD, TechPlan, Design, Implementation, Review, Test, Release, Bug-Linker, Retrospective, Orchestrator — each invokable as a Claude Code skill.
- **Living Tree dashboard** — 3D visualization of the org's BUDs, repos, and contributors, built on PlayCanvas with PBR lighting and KayKit characters.
- **MCP server** exposing 10 code-intelligence tools (`code_impact`, `code_query`, `code_context`, `code_community`, `code_god_nodes`, `code_stats`, plus 4 BUD/repo tools) to Claude Code and other MCP clients.
- **Multiplayer Colyseus room** — authoritative `OrgRoom` for shared 3D-world state, 20 Hz tick rate, with frontend interpolation.
- **Intake adapters** — Slack, Jira, and Linear feed external work items into Triage → BUD.
- **Dual deployment modes** — Full Docker (zero host deps, org-level API key) and Hybrid (host venv with hot reload, inherits `claude login` session).
- **Dual Claude auth** — `api_key` (Anthropic API token) or `hybrid_host` (host Claude Code session) per organization.
- **Prompt-caching + token optimization** — agent prompts use Anthropic prompt caching and structured tool-use to keep cost-per-BUD low.
- **Async job pattern** — backend returns `202` + job ID; frontend tracks via `useJobSocket` over `/ws/jobs/{job_id}`.
- **Event bus fan-out** — `event_bus.publish(...)` reaches in-process subscribers (dashboard `/ws`) and external transports (Colyseus, future Slack/metrics sinks) via a single `register_transport()` hook.
- **Bug auto-linking** — pgvector cosine search at 0.40 threshold links new bug reports to the BUDs that introduced them.
- **Contributor-XP economy** — closing a BUD awards XP and triggers a repo re-scan via the single `on_bud_closed()` entry point.
- **Apache 2.0 license + NOTICE** — explicit IP-independence statement; no AGPL remnants.
- **DCO sign-off workflow** — every commit requires `Signed-off-by:` via `git commit -s`.

### Security

- Secrets at rest encrypted with Fernet (AES-128) keyed per organization.
- All HTTP endpoints JWT-authenticated and org-scoped at the repository layer.

[Unreleased]: https://github.com/mickyarun/bodhiorchard/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/mickyarun/bodhiorchard/releases/tag/v0.1.0
