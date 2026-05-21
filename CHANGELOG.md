# Changelog

All notable changes to Bodhiorchard will be documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 1.0.0 (2026-05-21)


### Features

* add on_bud_development_started hook for dev-phase side effects ([ec0e7f8](https://github.com/mickyarun/bodhiorchard/commit/ec0e7f8265613e947c30996faa0bed9cc8d7b685))
* BUD ↔ Feature links UI, wireframe preview fixes, todo regen on chat edit ([bda65d8](https://github.com/mickyarun/bodhiorchard/commit/bda65d889bdc79b4e301a5a49fef20f018b67f2a))
* **bud-chat:** durable resume, cancel, and restart recovery for AI Editor chats ([#102](https://github.com/mickyarun/bodhiorchard/issues/102)) ([08bba0f](https://github.com/mickyarun/bodhiorchard/commit/08bba0f18508affdc564f70852ab1f07359bbdc0))
* **bud-chat:** session resume + stage-gate lock + concurrency + auto-trigger design ([#99](https://github.com/mickyarun/bodhiorchard/issues/99)) ([faa330c](https://github.com/mickyarun/bodhiorchard/commit/faa330c76d6aa573f91cbba1fee3f3ee8e30eb18))
* **bud:** phase-gated section edits + role fallback chain ([#98](https://github.com/mickyarun/bodhiorchard/issues/98)) ([25cf7a0](https://github.com/mickyarun/bodhiorchard/commit/25cf7a096ea4986b99eeba5128b8875ca0fdf5e4))
* **buds:** notion-style TODO board + agent-driven generation via job queue ([2655ee8](https://github.com/mickyarun/bodhiorchard/commit/2655ee85ba8944b2535721de18e329e16c2ff69d))
* **buds:** Notion-style TODO board + agent-driven generation via job queue ([8bd1739](https://github.com/mickyarun/bodhiorchard/commit/8bd17397803c96976494b50ea40e22117b314cbc))
* **code-review:** classify git-auth failures + retry-once + explicit cwd ([#126](https://github.com/mickyarun/bodhiorchard/issues/126)) ([5be2a18](https://github.com/mickyarun/bodhiorchard/commit/5be2a18f7206371795403e6e957439109fc5b246))
* **design-systems:** user customisations preserved across re-extraction ([#120](https://github.com/mickyarun/bodhiorchard/issues/120)) ([182c161](https://github.com/mickyarun/bodhiorchard/commit/182c161096440165a1d65188f4982cca7d3833ce))
* external-LLM mode + remote MCP endpoint + per-phase auto-generate ([#136](https://github.com/mickyarun/bodhiorchard/issues/136)) ([619329b](https://github.com/mickyarun/bodhiorchard/commit/619329b0644dbcd92b975046f70f2d0d4af31b1d))
* fire dev-phase hook on manual PATCH override too ([3974f77](https://github.com/mickyarun/bodhiorchard/commit/3974f77300cbe918f8479552de517898ac40f046))
* ground every BUD-stage agent in linked features + code_locations ([babe08d](https://github.com/mickyarun/bodhiorchard/commit/babe08d69930c8232f8c883cd8bb7ac2737ebce8))
* **landing:** sync hero, add Manifesto + FAQ, OG + Twitter + JSON-LD schema ([5feab76](https://github.com/mickyarun/bodhiorchard/commit/5feab76e8e672b17a5c19a40586ab5dea5c4c768))
* MCP-ify BUD design read/write + cascade reassignment to TODOs ([7e41ba8](https://github.com/mickyarun/bodhiorchard/commit/7e41ba83df6625da39462f73fa5291b5279f3d34))
* MCP-ify BUD design read/write, retire design_path ([d52a93a](https://github.com/mickyarun/bodhiorchard/commit/d52a93afc1717316aec5f0ab7b4badfb55503ad9))
* **mcp:** write-side BYO-AI tools + append-only BUD edit history ([#138](https://github.com/mickyarun/bodhiorchard/issues/138)) ([2b3559d](https://github.com/mickyarun/bodhiorchard/commit/2b3559d469268dcbdbc7346c168572545c4fb481))
* **pr-merge,features:** phase 5 Redis-stream redesign + lineage UI ([#103](https://github.com/mickyarun/bodhiorchard/issues/103)) ([4fd5ea6](https://github.com/mickyarun/bodhiorchard/commit/4fd5ea66b17fe50b7d76fd1c14748efa4926b1ea))
* production Docker setup for VPS deployment ([b919663](https://github.com/mickyarun/bodhiorchard/commit/b919663562202dcbc95db45578ab2d1878e23a5f))
* production Docker setup for VPS deployment ([1429072](https://github.com/mickyarun/bodhiorchard/commit/142907268e9439e515392505960a9bf7e90e4f41))
* public landing page at /landing/ ([a715cbb](https://github.com/mickyarun/bodhiorchard/commit/a715cbbf1e770d1ffbd0e4d1ab881b2a42deeba6))
* **qa:** allow reverting manual result to pending ([#141](https://github.com/mickyarun/bodhiorchard/issues/141)) ([33708f2](https://github.com/mickyarun/bodhiorchard/commit/33708f230b0eb964567b46a29265d6ee0300caa2))
* **scan,pr-merge:** route subsequent scans through the diff-based engine ([#106](https://github.com/mickyarun/bodhiorchard/issues/106)) ([21e27a7](https://github.com/mickyarun/bodhiorchard/commit/21e27a710b2a3951ec3e7fbd1ba88d06d1e9c457))
* **security:** layered defense for --dangerously-skip-permissions claude subprocess ([#92](https://github.com/mickyarun/bodhiorchard/issues/92)) ([984f466](https://github.com/mickyarun/bodhiorchard/commit/984f4661336546be1df39f830a1c027923e21b4e))
* **skills:** custom skills per agent type, per-BUD stage overrides, override-aware resolver ([#104](https://github.com/mickyarun/bodhiorchard/issues/104)) ([c02b5bb](https://github.com/mickyarun/bodhiorchard/commit/c02b5bbfe388487df149b06b98da83cc763ea487))
* surface BUD ↔ Feature links in Requirements tab + audit timeline ([2694cc1](https://github.com/mickyarun/bodhiorchard/commit/2694cc1a71835232b8de2e52eb7edf1faa67ff43))
* surface BUD ↔ Feature links in Requirements tab + audit timeline ([8c0895b](https://github.com/mickyarun/bodhiorchard/commit/8c0895be119e77a12d7eb82033f5ea7b17cfcd18))


### Bug Fixes

* actually hide trees on filter — disable sibling-rooted entities, not just container ([d23a75d](https://github.com/mickyarun/bodhiorchard/commit/d23a75d7847652765ea0032fbe522cf60d09a9bd))
* add missing networkx and graphifyy deps ([7cce3c5](https://github.com/mickyarun/bodhiorchard/commit/7cce3c59b7b91d416bbecbfe0e3c9cd0f259e2c2))
* add missing PyJWT dependency for GitHub App auth ([d9b2558](https://github.com/mickyarun/bodhiorchard/commit/d9b2558038a38439715f4ef5a7ca1d17f441cb5f))
* **bud-assignment:** phase-scope continuity to stop cross-phase bleed ([#135](https://github.com/mickyarun/bodhiorchard/issues/135)) ([2050ba8](https://github.com/mickyarun/bodhiorchard/commit/2050ba8a083fe8d5ea320852c28dff65f1fdccb9))
* **bud-design:** per-design cancel, per-repo banners, tracker loop fixes ([#101](https://github.com/mickyarun/bodhiorchard/issues/101)) ([7008eaf](https://github.com/mickyarun/bodhiorchard/commit/7008eafc0623189c7c8822aab81a400da1275a38))
* **buds:** render inline markdown in todo titles, stop truncation ([f10b8c8](https://github.com/mickyarun/bodhiorchard/commit/f10b8c8c2ad788eac36f06bf8a113c0f14ee9bf7))
* cascade BUD reassignment to non-taken-over TODOs with live refresh ([bbb3a4c](https://github.com/mickyarun/bodhiorchard/commit/bbb3a4c945ec508bc1287da81221fc7b68f61898))
* **ci:** unblock Dependabot PRs (hatchling pin + DCO bot exemption) ([#90](https://github.com/mickyarun/bodhiorchard/issues/90)) ([d52891c](https://github.com/mickyarun/bodhiorchard/commit/d52891c85f736cd74c5582575caacffeea289c8d))
* **claude-guard:** post-merge bug fixes — MCP, WebFetch, NPROC, env-exfil ([#93](https://github.com/mickyarun/bodhiorchard/issues/93)) ([6d72073](https://github.com/mickyarun/bodhiorchard/commit/6d720733bb5a9be2bee76b210bbc102b7ae5b7b7))
* dashboard remount crash and per-mount pc.AppBase leak ([22b9716](https://github.com/mickyarun/bodhiorchard/commit/22b9716eea7fd33b67b9e2a3dda49850b064dc2e))
* design wireframe preview — restore Vue mount, preserve handlers, contain link nav ([d35abf0](https://github.com/mickyarun/bodhiorchard/commit/d35abf0f62d1c6a279bb25de3c6ae67e64acee6c))
* **github:** post code-review on every re-run, not just the first ([#129](https://github.com/mickyarun/bodhiorchard/issues/129)) ([0a76289](https://github.com/mickyarun/bodhiorchard/commit/0a7628962754f71ad0bc464b9140bab758ba9c8b))
* **github:** preserve valid inline review comments on 422 ([#128](https://github.com/mickyarun/bodhiorchard/issues/128)) ([e5c3922](https://github.com/mickyarun/bodhiorchard/commit/e5c3922d1e5cddd983cf89a7c77dc2f948733cec))
* hide birds + disable pick/hover on user-hidden repos ([ba32c33](https://github.com/mickyarun/bodhiorchard/commit/ba32c33c9b4520e2b9f8c4768c26e977850df53f))
* hide birds + disable pick/hover on user-hidden repos ([51625c2](https://github.com/mickyarun/bodhiorchard/commit/51625c2a711b552e4a9bec3b018949ae63caa91e))
* hide repos via entity.enabled instead of full scene rebuild ([b09c68d](https://github.com/mickyarun/bodhiorchard/commit/b09c68d5c405e375c523e5d9dfff3ee97e374ba5))
* hide repos via entity.enabled instead of full scene rebuild ([b2ac1c0](https://github.com/mickyarun/bodhiorchard/commit/b2ac1c0a67151afc94b590189bfbf26de2c15cc7))
* **hooks:** resolve tracked repo by basename when laptop path misses ([#123](https://github.com/mickyarun/bodhiorchard/issues/123)) ([7eb2107](https://github.com/mickyarun/bodhiorchard/commit/7eb210703e87c897dba680cac38f9f1718fe444e))
* **landing:** re-skin to match Vue app's forest-green + gold palette ([d02b5c7](https://github.com/mickyarun/bodhiorchard/commit/d02b5c7bfdbd2b1973c873ec0b21df737cf9db47))
* **mcp-connect:** show full URL when VITE_API_BASE_URL is a bare path ([#137](https://github.com/mickyarun/bodhiorchard/issues/137)) ([d2c9f07](https://github.com/mickyarun/bodhiorchard/commit/d2c9f077e139a709efcbb5b0e50a601ad30452c4))
* **nginx:** proxy /mcp/ to backend so example-repo bridges can reach it ([#122](https://github.com/mickyarun/bodhiorchard/issues/122)) ([6ec5ca4](https://github.com/mickyarun/bodhiorchard/commit/6ec5ca48eb697d69ff59b4b995bf9d81486fb022))
* **qa-evidence:** always-visible delete button on evidence tile ([#140](https://github.com/mickyarun/bodhiorchard/issues/140)) ([c6eeac3](https://github.com/mickyarun/bodhiorchard/commit/c6eeac3cb82fb0285fffad39fdacb1d404886a1c))
* **rbac:** grant QA role buds:test for evidence upload + result entry ([#127](https://github.com/mickyarun/bodhiorchard/issues/127)) ([0273e52](https://github.com/mickyarun/bodhiorchard/commit/0273e523d488dca2ff8b951c94cec2278212c233))
* **rbac:** manager team:manage + developer buds:edit seed ([#107](https://github.com/mickyarun/bodhiorchard/issues/107)) ([a620827](https://github.com/mickyarun/bodhiorchard/commit/a62082709aeb8371150261b58d258c0bb53e2289))
* refetch linked features on every PM agent completion ([6af3d9d](https://github.com/mickyarun/bodhiorchard/commit/6af3d9d7c7454d18305b5cbadde785d5c7b33efc))
* regenerate BUD todos when tech arch is edited via chat ([7e2cf46](https://github.com/mickyarun/bodhiorchard/commit/7e2cf46f2f84947ee7787c02e4c35f9ffa5b921a))
* render character name labels in LAYERID_UI so path stones don't occlude ([52db562](https://github.com/mickyarun/bodhiorchard/commit/52db5621012c2d7290680b11b2219841965e0548))
* **scan:** include .bodhiorchard/mcp_bridge.py in bootstrap PR ([#121](https://github.com/mickyarun/bodhiorchard/issues/121)) ([1ee7cd1](https://github.com/mickyarun/bodhiorchard/commit/1ee7cd129f3800ee6cab9e7e8036b05f37d1b82d))
* **security:** block partial-SSRF in GitHub install-repo client ([#95](https://github.com/mickyarun/bodhiorchard/issues/95)) ([e75bdf3](https://github.com/mickyarun/bodhiorchard/commit/e75bdf32cef2848b2ddc6e63c603de67e858b657))
* **security:** safe_join helper + targeted path-injection guards ([#142](https://github.com/mickyarun/bodhiorchard/issues/142)) ([29d5a63](https://github.com/mickyarun/bodhiorchard/commit/29d5a63a493fa51bb9c3b50905784c9b7a2bb4e3))
* **security:** truncate password input to 72 bytes before bcrypt ([#100](https://github.com/mickyarun/bodhiorchard/issues/100)) ([1dbbac2](https://github.com/mickyarun/bodhiorchard/commit/1dbbac29c97dc8382ff8c01a348b741c0b12618e))
* **skills:** prune orphan agent_skills rows mis-tagged by step-4 fallback ([#105](https://github.com/mickyarun/bodhiorchard/issues/105)) ([5a02f09](https://github.com/mickyarun/bodhiorchard/commit/5a02f090db5eeca456859c52ea56d8fc105a1c14))
* **storage:** surface S3 errors as FileStorageError + bump success log ([#133](https://github.com/mickyarun/bodhiorchard/issues/133)) ([f183d42](https://github.com/mickyarun/bodhiorchard/commit/f183d4271a8f6ff4dc3af5740ee264c868a4517b))
* **webhook:** use webhook_event= kwarg to avoid structlog event collision ([#132](https://github.com/mickyarun/bodhiorchard/issues/132)) ([a0fbac3](https://github.com/mickyarun/bodhiorchard/commit/a0fbac3c8d1cba5e72aa00ea52e312d05964f759))
* **xp:** resolve PR author to BUD assignee when github_username misses ([#124](https://github.com/mickyarun/bodhiorchard/issues/124)) ([a88d4f0](https://github.com/mickyarun/bodhiorchard/commit/a88d4f0791508a2c7f0f81bcbe4847e9a1aafaf8))


### Performance Improvements

* branded loader, fix camera-drag lag, restore 60Hz garden motion ([33ba63a](https://github.com/mickyarun/bodhiorchard/commit/33ba63a9699f695446414cedb183c56529f3cf1b))
* **design:** real --resume + iteration_model + no-link fallback ([#89](https://github.com/mickyarun/bodhiorchard/issues/89)) ([ea3489a](https://github.com/mickyarun/bodhiorchard/commit/ea3489af621d975add15c63f576791930a721d2e))
* **todo-generator:** single-turn agent, no tools — ~30s → ~5-10s ([21c723f](https://github.com/mickyarun/bodhiorchard/commit/21c723f70e49c9538191dfbbba2280338064ae09))


### Reverts

* drop setup-PR debug instrumentation ([dc9ea26](https://github.com/mickyarun/bodhiorchard/commit/dc9ea26a244a616c6ff674959bdbc9a9031b29e4))
* drop setup-PR debug instrumentation (column, force-rerun, chip tooltip) ([b2907f4](https://github.com/mickyarun/bodhiorchard/commit/b2907f479b2b4a166187d87be6e2d9af71ab4ac2))

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
