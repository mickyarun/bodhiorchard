# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""CLI entrypoint for the cross-layer merge sandbox.

Run from the ``backend/`` directory using the project's venv:

    .venv/bin/python -m experiments.cross_layer_merge.run <command>

Commands:

    load      — create xlm_* tables, truncate, INSERT seed_data.json
    classify  — populate repo_layer/tech_stack/db_flavor on xlm_tracked_repo
    pair      — emit cross-layer pairs into xlm_pair_plan
    verify    — run Claude on each pending pair, apply merges
    report    — print before/after stats and merge log
    reset     — alias for ``load`` (re-truncates and re-inserts the seed)
"""

import argparse
import asyncio
import sys
from pathlib import Path

import structlog

from experiments.cross_layer_merge.classify.mode_detection import classify_all_repos
from experiments.cross_layer_merge.pair.planner import plan_pairs
from experiments.cross_layer_merge.pair.verifier import verify_all_pending
from experiments.cross_layer_merge.report.compare import render_report
from experiments.cross_layer_merge.report.render_html import render as render_html
from experiments.cross_layer_merge.seed.load_seed import reset_and_load

REPORT_HTML_PATH = Path(__file__).parent / "report" / "report.html"

log = structlog.get_logger(__name__)


async def _cmd_load() -> None:
    counts = await reset_and_load()
    print("Loaded:")
    for name, count in counts.items():
        print(f"  {name:30s} {count}")


async def _cmd_classify() -> None:
    results = await classify_all_repos()
    print("Classified:")
    for name, c in sorted(results.items()):
        tech = c.tech_stack or "-"
        db = c.db_flavor or "-"
        print(f"  {name:35s} layer={c.layer.value:10s} tech={tech:10s} db={db}")


async def _cmd_pair() -> None:
    count = await plan_pairs()
    print(f"Emitted {count} cross-layer pair(s) into xlm_pair_plan.")


async def _cmd_verify() -> None:
    summary = await verify_all_pending()
    print("Verifier summary:")
    for k, v in summary.items():
        print(f"  {k:25s} {v}")


async def _cmd_report() -> None:
    print(await render_report())


async def _cmd_report_html() -> None:
    html_doc = await render_html()
    REPORT_HTML_PATH.write_text(html_doc)
    print(f"Wrote report → {REPORT_HTML_PATH}")
    print(f"  open file://{REPORT_HTML_PATH}")


COMMANDS = {
    "load": _cmd_load,
    "reset": _cmd_load,  # alias — same operation
    "classify": _cmd_classify,
    "pair": _cmd_pair,
    "verify": _cmd_verify,
    "report": _cmd_report,
    "report-html": _cmd_report_html,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=list(COMMANDS.keys()))
    args = parser.parse_args(argv)
    asyncio.run(COMMANDS[args.command]())
    return 0


if __name__ == "__main__":
    sys.exit(main())
