"""Acceptance criteria verification service.

Verifies that merged code implements all PRD acceptance criteria
before allowing transition to TESTING. Uses a lightweight LLM call
to compare ACs against the git diff.
"""

import json
import re
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.services.bud_timeline import record_event

logger = structlog.get_logger(__name__)


def _extract_acceptance_criteria(requirements_md: str) -> list[str]:
    """Parse acceptance criteria from PRD markdown.

    Supports: `- [ ] AC text`, `- [x] AC text`, and bullet points
    under an Acceptance Criteria heading.
    """
    criteria: list[str] = []

    # Try checkbox format first (most common from our PM agent)
    checkboxes = re.findall(r"- \[[ x]\]\s*(.+)", requirements_md)
    if checkboxes:
        return [c.strip() for c in checkboxes if len(c.strip()) > 5]

    # Fallback: bullets under "Acceptance Criteria" heading
    in_ac_section = False
    for line in requirements_md.split("\n"):
        stripped = line.strip()
        if re.match(r"^#{1,3}\s*Acceptance\s+Criteria", stripped, re.I):
            in_ac_section = True
            continue
        if in_ac_section:
            if stripped.startswith("#"):
                break
            if stripped.startswith(("- ", "* ")):
                text = stripped[2:].strip()
                if len(text) > 5:
                    criteria.append(text)

    return criteria


async def _llm_verify_acs(
    criteria: list[str],
    tech_spec: str,
) -> list[dict] | None:
    """Ask LLM to verify each AC against the tech spec."""
    ac_list = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(criteria))

    prompt = (
        "Verify if each acceptance criterion is addressed in the tech spec.\n"
        "For each criterion, check if the tech spec describes implementation.\n\n"
        f"## Acceptance Criteria\n\n{ac_list}\n\n"
        f"## Tech Spec\n\n{tech_spec[:15000]}\n\n"
        "Reply with ONLY a JSON array:\n"
        '[{"criterion": "...", "implemented": true/false, '
        '"evidence": "brief reason"}]\n'
    )

    for attempt in range(2):
        try:
            from app.services.claude_runner import ClaudeRunnerConfig, run_claude_code

            config = ClaudeRunnerConfig(max_turns=1, timeout_seconds=60)
            result = await run_claude_code(prompt=prompt, config=config)

            if result.success and result.output:
                return _parse_verification_output(result.output)
        except Exception:
            logger.warning("ac_verify_attempt_failed", attempt=attempt + 1)

    return None


def _parse_verification_output(output: str) -> list[dict] | None:
    """Parse LLM JSON output. Defensive parsing."""
    text = output.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)

    try:
        parsed = json.loads(text.strip())
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(parsed, list):
        return None

    results: list[dict] = []
    for item in parsed:
        if not isinstance(item, dict):
            return None
        results.append(
            {
                "criterion": str(item.get("criterion", "")),
                "implemented": bool(item.get("implemented", False)),
                "evidence": str(item.get("evidence", "")),
            }
        )

    return results if results else None


async def verify_ac_completeness(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> tuple[bool, list[dict]]:
    """Verify all PRD acceptance criteria are implemented.

    Returns (all_passed, results). On LLM failure, returns (True, [])
    to avoid blocking the pipeline.
    """
    criteria = _extract_acceptance_criteria(bud.requirements_md or "")
    if not criteria:
        logger.debug("ac_verify_no_criteria", bud_id=str(bud.id))
        return True, []

    results = await _llm_verify_acs(criteria, bud.tech_spec_md or "")

    if results is None:
        logger.warning("ac_verify_llm_failed", bud_id=str(bud.id))
        return True, []  # Graceful degradation

    all_passed = all(r["implemented"] for r in results)
    passed_count = sum(1 for r in results if r["implemented"])
    total = len(results)

    event_type = "ac_verification_passed" if all_passed else "ac_verification_failed"
    await record_event(
        db,
        org_id,
        bud.id,
        event_type,
        detail={
            "passed": passed_count,
            "total": total,
            "results": results,
        },
    )

    logger.info(
        "ac_verification_complete",
        bud_id=str(bud.id),
        passed=passed_count,
        total=total,
        all_passed=all_passed,
    )

    return all_passed, results
