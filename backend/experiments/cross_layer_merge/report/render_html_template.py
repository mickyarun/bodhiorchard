# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# ruff: noqa: E501  -- embedded HTML/CSS strings; breaking mid-rule hurts readability

"""Static HTML/CSS chunks used by ``render_html``.

Kept separate so the renderer module stays focused on data shaping.
Edit copy/styling here; the renderer never has to change.

Sections rendered:

- **Stats strip** — headline numbers (synth rows, active KIs, multi-repo KIs %).
- **Per-repo summary** — synth-row count, KI count, single- vs multi-repo split.
- **Multi-repo KIs** — sorted by repo count desc; cross-repo consolidations.
- **Per-repo KI lists** — collapsible; spot over-fragmentation at a glance.
- **Pair verdicts** (existing) — only meaningful after a ``verify`` run.
"""

PAGE_SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Cross-Layer Merge Sandbox — Report</title>
<style>
  :root {{
    --bg: #0e1116; --panel: #161b22; --panel-2: #1f242c;
    --fg: #e6edf3; --dim: #8b949e; --line: #30363d;
    --green: #3fb950; --red: #f85149; --amber: #d29922;
    --blue: #58a6ff; --purple: #bc8cff;
  }}
  * {{ box-sizing: border-box; }}
  body {{ background: var(--bg); color: var(--fg); font: 14px/1.5 -apple-system, Segoe UI, sans-serif; margin: 0; padding: 24px; max-width: 1400px; margin-left: auto; margin-right: auto; }}
  h1 {{ margin: 0 0 8px; font-size: 22px; }}
  h2 {{ margin: 32px 0 12px; font-size: 16px; color: var(--blue); border-bottom: 1px solid var(--line); padding-bottom: 6px; }}
  h2 .count {{ color: var(--dim); font-weight: 400; font-size: 13px; margin-left: 8px; }}
  .dim {{ color: var(--dim); }}
  code {{ background: var(--panel-2); padding: 1px 6px; border-radius: 3px; font-size: 12px; }}

  /* Stats strip */
  .stats {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin: 16px 0; }}
  .stat {{ background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 12px; }}
  .stat .v {{ font-size: 24px; font-weight: 600; }}
  .stat .v.good {{ color: var(--green); }}
  .stat .v.warn {{ color: var(--amber); }}
  .stat .l {{ color: var(--dim); font-size: 12px; text-transform: uppercase; letter-spacing: .5px; }}
  .stat .sub {{ color: var(--dim); font-size: 11px; margin-top: 2px; }}

  /* Calibration band */
  .calibration {{ background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 10px 14px; margin-bottom: 16px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; font-size: 13px; }}
  .cal-pill {{ background: var(--panel-2); color: var(--purple); padding: 4px 10px; border-radius: 12px; font-size: 12px; }}
  .cal-pill strong {{ color: var(--fg); margin-left: 4px; }}

  /* Repo cards (classification) */
  .repos {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
  .repo {{ background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 12px; }}
  .repo .name {{ font-weight: 600; }}
  .repo .meta {{ color: var(--dim); font-size: 12px; margin-top: 6px; }}
  .repo .stats-line {{ font-size: 12px; margin-top: 6px; display: flex; gap: 12px; }}
  .repo .stats-line span strong {{ color: var(--fg); }}
  .layer {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; text-transform: uppercase; }}
  .layer.frontend {{ background: #1f3a5c; color: #79c0ff; }}
  .layer.backend {{ background: #2c3a1f; color: #b9e35a; }}
  .layer.processor {{ background: #3a2c1f; color: #ffa657; }}
  .layer.shared, .layer.unclassified {{ background: #2c2c2c; color: var(--dim); }}

  /* Multi-repo KI table */
  table.kis {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  table.kis th, table.kis td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--line); vertical-align: top; }}
  table.kis th {{ font-size: 11px; text-transform: uppercase; letter-spacing: .5px; color: var(--dim); font-weight: 500; background: var(--panel); }}
  table.kis tr:hover {{ background: var(--panel-2); }}
  table.kis td.count {{ width: 70px; text-align: center; font-weight: 600; color: var(--green); font-size: 18px; }}
  table.kis td.cross-layer-count {{ color: var(--purple); }}
  .repo-chip {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; margin: 2px 4px 2px 0; background: var(--panel-2); border: 1px solid var(--line); }}
  .repo-chip.frontend {{ background: #1f3a5c; color: #79c0ff; border-color: #1f3a5c; }}
  .repo-chip.backend {{ background: #2c3a1f; color: #b9e35a; border-color: #2c3a1f; }}
  .repo-chip.processor {{ background: #3a2c1f; color: #ffa657; border-color: #3a2c1f; }}
  .repo-chip.shared {{ background: #2c2c2c; color: var(--dim); }}

  /* Per-repo KI lists */
  details.repo-section {{ background: var(--panel); border: 1px solid var(--line); border-radius: 6px; margin-bottom: 8px; }}
  details.repo-section > summary {{ list-style: none; padding: 10px 14px; cursor: pointer; display: flex; align-items: center; gap: 12px; }}
  details.repo-section > summary::-webkit-details-marker {{ display: none; }}
  details.repo-section > summary::before {{ content: "▶"; color: var(--dim); font-size: 10px; transition: transform .15s; }}
  details.repo-section[open] > summary::before {{ transform: rotate(90deg); }}
  details.repo-section[open] > summary {{ border-bottom: 1px solid var(--line); }}
  .repo-section .body {{ padding: 8px 14px 14px; }}
  .ki-row {{ padding: 6px 0; border-bottom: 1px dotted var(--line); display: flex; justify-content: space-between; align-items: center; }}
  .ki-row:last-child {{ border-bottom: none; }}
  .ki-row .title {{ flex: 1; }}
  .ki-row .badges {{ font-size: 11px; color: var(--dim); }}
  .ki-row.shared .title::before {{ content: "↔ "; color: var(--green); font-weight: 700; }}

  /* Cluster merge decisions */
  details.merge-decision {{ background: var(--panel); border: 1px solid var(--line); border-radius: 6px; margin-bottom: 8px; }}
  details.merge-decision > summary {{ list-style: none; padding: 10px 14px; cursor: pointer; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }}
  details.merge-decision > summary::-webkit-details-marker {{ display: none; }}
  details.merge-decision > summary::before {{ content: "▶"; color: var(--dim); font-size: 10px; transition: transform .15s; }}
  details.merge-decision[open] > summary::before {{ transform: rotate(90deg); }}
  details.merge-decision[open] > summary {{ border-bottom: 1px solid var(--line); }}
  .merge-decision .canonical {{ font-weight: 600; flex: 1; }}
  .decision-body {{ padding: 12px 16px; }}
  .decision-body .label {{ color: var(--dim); font-size: 11px; text-transform: uppercase; letter-spacing: .5px; margin-bottom: 4px; }}
  .decision-body .rationale-block {{ background: var(--panel-2); padding: 10px 12px; border-radius: 4px; margin-bottom: 12px; font-style: italic; color: var(--fg); }}
  .decision-body .cluster-block {{ margin-bottom: 12px; }}
  .decision-body ul {{ list-style: none; padding: 0; margin: 0; }}
  .decision-body li {{ padding: 6px 8px; background: var(--panel-2); border-radius: 4px; margin-bottom: 4px; display: flex; gap: 8px; align-items: center; }}
  .decision-body li.absorbed {{ background: #1f3a2c; }}
  .decision-body li.canonical-row {{ background: #1f2c3a; border-left: 3px solid var(--blue); }}
  details.raw-prompt {{ background: var(--bg); border: 1px solid var(--line); border-radius: 4px; margin-top: 12px; }}
  details.raw-prompt > summary {{ padding: 8px 12px; cursor: pointer; }}
  details.raw-prompt pre {{ padding: 12px; margin: 0; font-size: 11px; line-height: 1.4; white-space: pre-wrap; word-wrap: break-word; max-height: 400px; overflow-y: auto; border-top: 1px solid var(--line); }}
  details.raw-prompt pre.response {{ background: var(--panel-2); }}

  /* Pair section (legacy verify flow) */
  details.pair {{ background: var(--panel); border: 1px solid var(--line); border-radius: 6px; margin-bottom: 12px; }}
  details.pair > summary {{ list-style: none; padding: 12px 16px; cursor: pointer; display: flex; align-items: center; gap: 12px; }}
  details.pair > summary::-webkit-details-marker {{ display: none; }}
  details.pair > summary::before {{ content: "▶"; color: var(--dim); font-size: 10px; transition: transform .15s; }}
  details.pair[open] > summary::before {{ transform: rotate(90deg); }}
  details.pair[open] > summary {{ border-bottom: 1px solid var(--line); }}
  .pair-body {{ padding: 12px 16px; }}
  .pair-pair {{ font-weight: 600; }}
  .pair-meta {{ margin-left: auto; color: var(--dim); font-size: 12px; }}
  .status {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; text-transform: uppercase; }}
  .status.done {{ background: #1f3a2c; color: var(--green); }}
  .status.running {{ background: #3a2c1f; color: var(--amber); }}
  .status.failed {{ background: #3a1f1f; color: var(--red); }}
  .status.pending {{ background: #2c2c2c; color: var(--dim); }}
  .verdict {{ display: grid; grid-template-columns: 2fr 3fr 110px; gap: 16px; padding: 12px; border-top: 1px solid var(--line); align-items: start; }}
  .verdict:first-child {{ border-top: none; }}
  .verdict .source {{ background: var(--panel-2); padding: 10px; border-radius: 4px; }}
  .verdict .source .label {{ color: var(--dim); font-size: 11px; text-transform: uppercase; letter-spacing: .5px; }}
  .verdict .candidates ul {{ list-style: none; padding: 0; margin: 0; }}
  .verdict .candidates li {{ padding: 6px 8px; border-radius: 4px; margin-bottom: 4px; background: var(--panel-2); }}
  .verdict .candidates li.absorbed {{ background: #1f3a2c; }}
  .tag {{ background: var(--green); color: var(--bg); font-size: 10px; padding: 1px 6px; border-radius: 8px; font-weight: 600; }}
  .action {{ text-align: center; padding-top: 8px; }}
  .action-pill {{ display: inline-block; padding: 4px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; text-transform: uppercase; }}
  .action-pill.merge {{ background: #1f3a2c; color: var(--green); }}
  .action-pill.no_match {{ background: #2c2c2c; color: var(--dim); }}
  .rationale {{ grid-column: 1 / -1; color: var(--dim); font-size: 12px; padding: 0 4px; font-style: italic; }}
</style>
</head>
<body>
<h1>Cross-Layer Merge Sandbox — Report</h1>
<p class="dim">Run <code>copy-from-prod → classify → merge → report-html</code> and refresh.
Multi-repo KI fraction is the headline metric — higher means more cross-repo features got consolidated.</p>

<div class="stats">
  <div class="stat"><div class="v">{synth_rows}</div><div class="l">Synth rows</div></div>
  <div class="stat"><div class="v">{active_ki}</div><div class="l">Active KIs</div></div>
  <div class="stat"><div class="v {multi_repo_class}">{multi_repo}</div><div class="l">Multi-repo KIs</div><div class="sub">{multi_repo_pct}%</div></div>
  <div class="stat"><div class="v">{absorbed_synth}</div><div class="l">Synth rows folded</div><div class="sub">→ existing canonical</div></div>
  <div class="stat"><div class="v">{cross_layer_kis}</div><div class="l">Cross-layer KIs</div><div class="sub">spans ≥2 layers</div></div>
  <div class="stat"><div class="v">{inactive_ki}</div><div class="l">Deactivated</div></div>
</div>

<div class="calibration">
  <span class="dim">Auto-calibrated thresholds (last merge run):</span>
  <span class="cal-pill">same-layer ≥ <strong>{same_layer_threshold}</strong></span>
  <span class="cal-pill">cross-layer ≥ <strong>{cross_layer_threshold}</strong></span>
  <span class="dim">— picked from this org's pairwise cosine distribution (p99.5 / p99.0)</span>
</div>

<h2>Repos <span class="count">{repo_count} active</span></h2>
<div class="repos">{repos}</div>

<h2>Multi-repo KIs <span class="count">{multi_repo_count} consolidated across ≥2 repos</span></h2>
{multi_repo_table}

<h2>KIs by repo <span class="count">click a repo to expand its KI list</span></h2>
{per_repo_sections}

<h2>Cluster merge decisions <span class="count">{merge_log_count} Claude calls in last run</span></h2>
{merge_log}

<h2>Pair verdicts (legacy verify flow) <span class="count">runs only after `pair`+`verify`</span></h2>
{pairs}
</body>
</html>
"""

REPO_CARD = """<div class="repo">
  <div class="name">{name}</div>
  <div><span class="layer {layer_class}">{layer}</span></div>
  <div class="meta">tech: {tech} · db: {db}</div>
  <div class="stats-line">
    <span><strong>{synth_count}</strong> <span class="dim">synth</span></span>
    <span><strong>{ki_count}</strong> <span class="dim">KIs</span></span>
    <span><strong>{shared_count}</strong> <span class="dim">shared</span></span>
  </div>
</div>"""

# One row per multi-repo KI in the table.
MULTI_REPO_KI_ROW = """<tr>
  <td class="count">{repo_count}</td>
  <td>{title}</td>
  <td>{repo_chips}</td>
</tr>"""

MULTI_REPO_KI_TABLE = """<table class="kis">
  <thead><tr><th>Repos</th><th>Title</th><th>Spans</th></tr></thead>
  <tbody>{rows}</tbody>
</table>"""

# One collapsible section per repo, listing every KI linked to that repo.
PER_REPO_SECTION = """<details class="repo-section">
  <summary>
    <span><strong>{repo_name}</strong></span>
    <span class="layer {layer_class}">{layer}</span>
    <span class="dim">{ki_count} KIs · {shared_count} shared with other repos</span>
  </summary>
  <div class="body">{rows}</div>
</details>"""

PER_REPO_KI_ROW = """<div class="ki-row {shared_class}">
  <span class="title">{title}</span>
  <span class="badges">{other_repos}</span>
</div>"""

# One <details> per Claude cluster decision in the audit log.
MERGE_LOG_ROW = """<details class="merge-decision">
  <summary>
    <span class="action-pill {action_class}">{action}</span>
    <span class="canonical">{canonical_title}</span>
    <span class="dim">cluster size: {cluster_size} · absorbed: {absorbed_count}</span>
  </summary>
  <div class="decision-body">
    <div class="rationale-block"><strong>Rationale:</strong> {rationale}</div>
    <div class="cluster-block">
      <div class="label">Cluster members</div>
      <ul>{member_list}</ul>
    </div>
    {related_block}
    <details class="raw-prompt">
      <summary class="dim">Show prompt + raw response</summary>
      <pre class="prompt">{prompt}</pre>
      <pre class="response">{response}</pre>
    </details>
  </div>
</details>"""

PAIR_CARD = """<details class="pair" {open_attr}>
  <summary>
    <span class="pair-pair">{repo_a} &harr; {repo_b}</span>
    <span class="dim">{kind}</span>
    <span class="status {status_class}">{status}</span>
    <span class="pair-meta">{verdict_count} verdicts · {merged_count} merged · {elapsed}</span>
  </summary>
  <div class="pair-body">{verdicts}</div>
</details>""".replace("{open_attr}", "")  # always closed by default; user clicks to expand

VERDICT_ROW = """<div class="verdict">
  <div class="source">
    <div class="label">SOURCE — {source_repo}</div>
    <div>{source_title}</div>
  </div>
  <div class="candidates">
    <div class="label dim" style="font-size:11px;text-transform:uppercase;letter-spacing:.5px">Candidates</div>
    <ul>{candidates}</ul>
  </div>
  <div class="action"><span class="action-pill {action_class}">{action}</span></div>
  <div class="rationale">{rationale}</div>
</div>"""
