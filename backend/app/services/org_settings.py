"""Single source of truth for per-org QA and BUD stage settings.

Settings that change BUD lifecycle behaviour (QA automation framework,
UAT stage on/off) live in the ``organizations.config`` JSONB column under
the ``qa`` and ``bud_stages`` keys. This module is the ONLY place in the
backend that reads those keys — every service needing them must go through
``get_qa_settings`` / ``get_bud_stage_settings`` / ``get_phase_order`` so
we have one defaulting rule, one key name, and one place to change.

The Pydantic classes returned here are imported verbatim from
``app.schemas.settings`` so there is exactly ONE definition of each model
in the backend. The schema classes carry the write-path validation (e.g.
the prompt-injection regex on ``framework``); stored data is already
validated when it reaches this module, so we just construct the same
class with the persisted values and the shipped defaults fill any gaps.
"""

from app.schemas.settings import BUDStageSettings, QAAutomationSettings
from app.services.estimation_engine import PHASE_ORDER


def get_qa_settings(org_config: dict | None) -> QAAutomationSettings:
    """Resolve QA settings from an organization config dict.

    Accepts ``None`` / missing / partial ``qa`` sections and fills in the
    shipped defaults. Never raises on missing keys — a fresh org with no
    qa section behaves identically to one with the defaults saved.

    Args:
        org_config: The raw ``organization.config`` JSONB dict, or None.

    Returns:
        A ``QAAutomationSettings`` with all fields populated.
    """
    raw = (org_config or {}).get("qa") or {}
    return QAAutomationSettings(**raw)


def get_bud_stage_settings(org_config: dict | None) -> BUDStageSettings:
    """Resolve BUD stage settings from an organization config dict.

    Args:
        org_config: The raw ``organization.config`` JSONB dict, or None.

    Returns:
        A ``BUDStageSettings`` with all fields populated.
    """
    raw = (org_config or {}).get("bud_stages") or {}
    return BUDStageSettings(**raw)


def is_uat_enabled(org_config: dict | None) -> bool:
    """Return whether the org includes a UAT stage in its BUD lifecycle.

    Thin wrapper so callers that only care about the single boolean don't
    have to import / construct the whole settings object.
    """
    return get_bud_stage_settings(org_config).uat_enabled


def get_phase_order(org_config: dict | None) -> list[str]:
    """Return the BUD phase order for this org, filtered by toggles.

    Delegates to the canonical ``PHASE_ORDER`` in ``estimation_engine`` and
    strips any phases the org has disabled. Used by
    ``bud_estimation.estimate_bud_dates`` (to drive PERT/Monte Carlo over
    the right phase set) and by the frontend ``usePhaseOrder`` composable
    mirror (which applies the same filter on the client).
    """
    if is_uat_enabled(org_config):
        return list(PHASE_ORDER)
    return [p for p in PHASE_ORDER if p != "uat"]
