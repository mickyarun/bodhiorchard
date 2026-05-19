<!-- bodhi-codeintel:start -->
# Code Intelligence — bodhi indexer

This project is indexed by bodhiorchard's own code-graph indexer
(`backend/app/services/code_indexer/`, MIT-licensed graphify under the
hood). The cached call graph is stored in Postgres (`repo_graph_cache`) and
exposed to Claude Code through the `code_*` MCP tool group.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, call `code_impact({target: "symbolName", direction: "upstream", repo_id: "<uuid>"})` and report the blast radius (direct callers, affected files) to the user.
- **MUST warn the user** if impact returns more than ~20 callers across multiple modules — that's the high-risk signal.
- When exploring unfamiliar code, use `code_query({query: "concept", repo_id: "<uuid>"})` to find candidate symbols by name. Pair with `code_context` for caller/callee details.
- For "what's in this feature?" questions, use `code_community({cluster_id: "c0", repo_id: "<uuid>"})` — returns every file and symbol in a domain cluster.

## Never Do

- NEVER edit a function, class, or method without first running `code_impact` on it.
- NEVER rename symbols with find-and-replace — the call graph is the source of truth for usage sites.
- NEVER manually edit `cluster_cache` or `repo_graph_cache` rows; they're derived state owned by the scan pipeline.

## MCP tools

| Tool | Purpose |
|------|---------|
| `code_impact` | Upstream/downstream BFS from a symbol (blast-radius check) |
| `code_query` | Substring search across symbol labels + file paths |
| `code_context` | Single-symbol 360°: attributes, callers, callees |
| `code_community` | List nodes/files in one cluster (e.g. `c0`) |
| `code_god_nodes` | Top-N highest-degree hubs (refactoring candidates) |
| `code_stats` | Graph stats + language extension distribution |

The indexer runs in Stage 0 (`ingest`) of every scan and stays SHA-keyed,
so re-runs on the same `head_sha` short-circuit through `cluster_cache` /
`repo_graph_cache` without re-parsing.

<!-- bodhi-codeintel:end -->

## BUD `auto_generate` flag

Each `bud_documents` row carries an `auto_generate: bool` (default `true`).
When `false`, NO stage agent (PM / Designer / TechPlanner / Tester) is
auto-spawned on BUD creation or stage transition — the user drives PRD /
design / tech-spec content with their own local AI through the read-only
remote MCP endpoint (see `MCP-REMOTE.md`).

Implications when working in this codebase:

- Never check `bud.status` alone to decide whether to spawn an agent;
  always also check `bud.auto_generate`. The two gating sites are
  `api/v1/bud.py:create_bud` and `api/v1/bud.py:_trigger_status_jobs`.
- The explicit `code-review/override` endpoint deliberately ignores
  `auto_generate` — it's a manual user escalation, not auto-triggering.
- If you add a new auto-spawn site, gate it the same way and write a
  log entry on the skip path (existing skips log
  `stage_agent_skip_auto_generate_off`).
