# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar
# ruff: noqa: E501  -- embedded HTML/CSS strings; breaking mid-rule hurts readability

"""Static HTML/CSS chunks used by ``render_html``.

Kept separate so the renderer module stays focused on data shaping.
Edit copy/styling here; the renderer never has to change.
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
  body {{ background: var(--bg); color: var(--fg); font: 14px/1.5 -apple-system, Segoe UI, sans-serif; margin: 0; padding: 24px; }}
  h1 {{ margin: 0 0 8px; font-size: 22px; }}
  h2 {{ margin: 32px 0 12px; font-size: 16px; color: var(--blue); }}
  .dim {{ color: var(--dim); }}
  .stats {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin: 16px 0; }}
  .stat {{ background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 12px; }}
  .stat .v {{ font-size: 24px; font-weight: 600; }}
  .stat .l {{ color: var(--dim); font-size: 12px; text-transform: uppercase; letter-spacing: .5px; }}
  .repos {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }}
  .repo {{ background: var(--panel); border: 1px solid var(--line); border-radius: 6px; padding: 12px; }}
  .repo .name {{ font-weight: 600; }}
  .repo .meta {{ color: var(--dim); font-size: 12px; margin-top: 6px; }}
  .layer {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; text-transform: uppercase; }}
  .layer.frontend {{ background: #1f3a5c; color: #79c0ff; }}
  .layer.backend {{ background: #2c3a1f; color: #b9e35a; }}
  .layer.processor {{ background: #3a2c1f; color: #ffa657; }}
  .layer.shared, .layer.unclassified {{ background: #2c2c2c; color: var(--dim); }}
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
<p class="dim">Refresh this page after each <code>run.py verify</code> to see new verdicts.</p>

<div class="stats">
  <div class="stat"><div class="v">{active_ki}</div><div class="l">Active KIs</div></div>
  <div class="stat"><div class="v">{inactive_ki}</div><div class="l">Absorbed</div></div>
  <div class="stat"><div class="v">{multi_repo}</div><div class="l">Multi-repo ({multi_repo_pct}%)</div></div>
  <div class="stat"><div class="v">{pairs_done}</div><div class="l">Pairs done</div></div>
  <div class="stat"><div class="v">{pairs_failed}</div><div class="l">Pairs failed</div></div>
  <div class="stat"><div class="v">{total_merges}</div><div class="l">Total merges</div></div>
</div>

<h2>Repos</h2>
<div class="repos">{repos}</div>

<h2>Pairs &amp; verdicts</h2>
{pairs}
</body>
</html>
"""

REPO_CARD = """<div class="repo">
  <div class="name">{name}</div>
  <div><span class="layer {layer_class}">{layer}</span></div>
  <div class="meta">tech: {tech} · db: {db}</div>
</div>"""

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
