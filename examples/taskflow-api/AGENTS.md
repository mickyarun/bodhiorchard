<!-- bodhi-codeintel:start -->
# Code Intelligence — bodhi indexer

This project is indexed by bodhiorchard's own code-graph indexer
(graphify under the hood). Use the `code_*` MCP tools to understand
code, assess impact, and navigate safely.

## Always Do

- **MUST run impact analysis before editing any symbol.** Call
  `code_impact({target: "symbolName", direction: "upstream", repo_id})`
  and report the blast radius (direct callers, affected files) to the user.
- When exploring unfamiliar code, use `code_query({query: "concept", repo_id})`
  to find candidate symbols by name. Pair with `code_context` for
  caller/callee details.
- For "what's in this feature?" questions, use
  `code_community({cluster_id: "c0", repo_id})` — returns every file
  and symbol in a domain cluster.

## Never Do

- NEVER edit a function, class, or method without first running `code_impact` on it.
- NEVER rename symbols with find-and-replace — the call graph is the source of truth.

## MCP tools

| Tool | Purpose |
|------|---------|
| `code_impact` | Upstream/downstream BFS from a symbol (blast-radius check) |
| `code_query` | Substring search across symbol labels + file paths |
| `code_context` | Single-symbol 360°: attributes, callers, callees |
| `code_community` | List nodes/files in one cluster (e.g. `c0`) |
| `code_god_nodes` | Top-N highest-degree hubs (refactoring candidates) |
| `code_stats` | Graph stats + language extension distribution |
<!-- bodhi-codeintel:end -->