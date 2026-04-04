"""LLM integration for PERT three-point estimation.

Handles prompt building, LLM calls, and defensive JSON parsing.
Separated from bud_estimation.py for modularity and testability.
"""

import json
import re

import structlog

from app.models.bud import BUDDocument
from app.services.estimation_engine import PERTEstimate

logger = structlog.get_logger(__name__)


def build_estimation_prompt(
    bud: BUDDocument,
    complexity: int,
    backlog_ctx: dict,
    skill_ctx: dict | None,
    historical_ctx: str,
    remaining_phases: list[str],
) -> str:
    """Build the LLM prompt for PERT three-point estimation."""
    repos = bud.impacted_repos or []
    repo_names = ", ".join(r.get("repo_name", "?") for r in repos) or "unknown"

    skill_block = ""
    if skill_ctx:
        details = skill_ctx.get("skill_details", [])
        skill_lines = [
            f"  - {d['module']}: score {d['score']:.2f}, {d['touches']} touches" for d in details
        ]
        skill_block = (
            f"\nDeveloper skills ({len(details)} modules known):\n"
            + "\n".join(skill_lines)
            + f"\nAvg skill score: {skill_ctx['avg_skill_score']:.2f}\n"
        )

    phases_str = ", ".join(remaining_phases)

    # Build phase-specific context based on what content exists
    phase_context = _build_phase_context(bud)

    return (
        "You are estimating software delivery phases in BUSINESS DAYS.\n"
        "For each phase, provide Optimistic (O), Most Likely (M), and "
        "Pessimistic (P) estimates.\n"
        "Also rate overall feature complexity from 1 (trivial) to 5 (very complex).\n\n"
        f"Impacted repos: {len(repos)} ({repo_names})\n"
        f"Backlog ahead: {backlog_ctx['queue_depth']} features\n"
        f"Assignee workload: {backlog_ctx['assignee_workload']} other active\n"
        f"{phase_context}"
        f"{skill_block}"
        f"{historical_ctx}\n\n"
        f"Estimate these remaining phases: {phases_str}\n"
        "The first phase listed may already be in progress — estimate REMAINING time.\n"
        "If a phase is already complete, use O=0, M=0, P=0.\n"
        "This team uses AI-assisted development (Claude Code) — factor that in.\n\n"
        "Reply with ONLY a JSON object. Example:\n"
        '{"complexity": 2, "phases": {"development": {"O": 1, "M": 2, "P": 4}, '
        '"testing": {"O": 0.5, "M": 1, "P": 2}}}\n'
    )


def _build_phase_context(bud: BUDDocument) -> str:
    """Build context from BUD artifacts for the estimation LLM.

    Passes full PRD + tech spec content (capped at 20K each) and an
    extracted summary from design wireframe HTML.
    """
    lines: list[str] = []

    # PRD — full content (cap 20K)
    req = bud.requirements_md or ""
    if req:
        lines.append("PRD content:")
        lines.append(req[:20000])
    else:
        lines.append("PRD: not yet generated")

    # Design — extracted summary (raw HTML is too large)
    designs = bud.designs or []
    ready = [d for d in designs if getattr(d, "status", "") == "ready"]
    if ready:
        lines.append(f"Designs: {len(ready)} wireframes ready")
        for d in ready:
            summary = _summarize_design_html(getattr(d, "design_html", "") or "")
            if summary:
                lines.append(summary)
    elif designs:
        lines.append(f"Designs: {len(designs)} in progress")

    # Tech spec — full content (cap 20K)
    spec = bud.tech_spec_md or ""
    if spec:
        lines.append("Tech spec content:")
        lines.append(spec[:20000])
    else:
        lines.append("Tech spec: not yet generated")

    # QA test cases — count
    auto = bud.qa_automation_cases or []
    manual = bud.qa_manual_cases or []
    if auto or manual:
        lines.append(f"QA: {len(auto)} automation + {len(manual)} manual test cases")

    return "\n".join(lines) + "\n"


def _summarize_design_html(html: str) -> str:
    """Extract estimation-relevant signals from wireframe HTML."""
    if not html:
        return ""
    annotations = re.findall(r"<!--\s*([A-Z][\w-]*:.+?)-->", html)
    buttons = len(re.findall(r"<(?:button|v-btn)[^>]*>", html, re.I))
    inputs = len(re.findall(r"<(?:input|v-text-field|select|textarea)[^>]*>", html, re.I))
    parts: list[str] = []
    if annotations:
        parts.append(f"  Wireframe annotations: {len(annotations)}")
        for a in annotations[:8]:
            parts.append(f"    - {a.strip()}")
    if buttons:
        parts.append(f"  Interactive elements: {buttons} buttons")
    if inputs:
        parts.append(f"  Form inputs: {inputs}")
    return "\n".join(parts)


class LLMEstimateResult:
    """Result from LLM estimation: PERT estimates + LLM-rated complexity."""

    def __init__(
        self,
        phases: dict[str, PERTEstimate],
        complexity: int | None = None,
    ) -> None:
        self.phases = phases
        self.complexity = complexity


async def llm_pert_estimate(
    bud: BUDDocument,
    complexity: int,
    backlog_ctx: dict,
    skill_ctx: dict | None,
    historical_ctx: str,
    remaining_phases: list[str],
) -> LLMEstimateResult | None:
    """Call LLM for PERT estimates + complexity. Returns None on failure."""
    prompt = build_estimation_prompt(
        bud,
        complexity,
        backlog_ctx,
        skill_ctx,
        historical_ctx,
        remaining_phases,
    )

    for attempt in range(2):
        try:
            from app.services.claude_runner import ClaudeRunnerConfig, run_claude_code

            config = ClaudeRunnerConfig(max_turns=1, timeout_seconds=60)
            result = await run_claude_code(prompt=prompt, config=config)

            if result.success and result.output:
                return parse_llm_pert_output(result.output, remaining_phases)
        except Exception:
            logger.warning(
                "llm_pert_attempt_failed",
                attempt=attempt + 1,
                bud_id=str(bud.id),
            )

    return None


def parse_llm_pert_output(
    output: str,
    remaining_phases: list[str],
) -> LLMEstimateResult | None:
    """Parse LLM JSON into PERT estimates + complexity. Defensive parsing."""
    text = output.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)

    try:
        parsed = json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(parsed, dict):
        return None

    # Extract complexity (1-5) from top level
    llm_complexity: int | None = None
    raw_cx = parsed.get("complexity")
    if isinstance(raw_cx, (int, float)) and 1 <= raw_cx <= 5:
        llm_complexity = round(raw_cx)

    # Phase estimates live under "phases" key (new format)
    # or at top level (backward compat with old format)
    phases_data = parsed.get("phases", parsed)
    if not isinstance(phases_data, dict):
        return None

    result: dict[str, PERTEstimate] = {}
    for phase in remaining_phases:
        phase_data = phases_data.get(phase)
        if not isinstance(phase_data, dict):
            return None
        try:
            o = float(phase_data["O"])
            m = float(phase_data["M"])
            p = float(phase_data["P"])
            if not (0 <= o <= m <= p <= 365):
                return None
            result[phase] = PERTEstimate(o, m, p)
        except (KeyError, TypeError, ValueError):
            return None

    return LLMEstimateResult(phases=result, complexity=llm_complexity)

    return result
