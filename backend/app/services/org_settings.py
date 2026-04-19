# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Single source of truth for per-org QA, BUD stage, and presence settings.

Settings that change BUD lifecycle behaviour (QA automation framework,
UAT stage on/off) and presence-inference behaviour (working days, hours,
timezone, auto-mode toggle) live in the ``organizations.config`` JSONB
column under the ``qa``, ``bud_stages``, and ``presence`` keys. This
module is the ONLY place in the backend that reads those keys — every
service needing them must go through ``get_qa_settings`` /
``get_bud_stage_settings`` / ``get_phase_order`` / ``get_presence_settings``
so we have one defaulting rule, one key name, and one place to change.

The Pydantic classes returned here are imported verbatim from
``app.schemas.settings`` so there is exactly ONE definition of each model
in the backend. The schema classes carry the write-path validation (e.g.
the prompt-injection regex on ``framework``, the IANA timezone whitelist
on ``timezone``); stored data is already validated when it reaches this
module, so we just construct the same class with the persisted values
and the shipped defaults fill any gaps.
"""

from app.schemas.settings import (
    BUDStageSettings,
    JiraSettings,
    PresenceSettings,
    QAAutomationSettings,
)
from app.services.estimation_engine import PHASE_ORDER

# Shipped defaults as a module-level constant so callers that need the
# raw dict (e.g. the internal_colyseus snapshot payload) do not pay the
# Pydantic construction cost on every request.
DEFAULT_PRESENCE_SETTINGS: PresenceSettings = PresenceSettings()


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


def get_presence_settings(org_config: dict | None) -> PresenceSettings:
    """Resolve per-org presence-inference settings from an organization config dict.

    Accepts ``None`` / missing / partial ``presence`` sections and fills
    in the shipped defaults. A fresh org with no presence section is
    indistinguishable from one that saved the defaults explicitly, which
    preserves the legacy hardcoded behaviour (Mon-Fri, 08:00-18:00,
    server-local time) for orgs that never visit the settings page.

    **Defensive:** if the stored JSON is corrupt (e.g. empty working_days
    from a pre-validation write, or a removed IANA timezone), this catches
    the ``ValidationError`` and returns ``DEFAULT_PRESENCE_SETTINGS``
    instead of letting the error propagate into callers like
    ``refresh_all_presence`` which iterate all orgs in a shared loop.

    Args:
        org_config: The raw ``organization.config`` JSONB dict, or None.

    Returns:
        A ``PresenceSettings`` with all fields populated.
    """
    raw = (org_config or {}).get("presence") or {}
    try:
        return PresenceSettings(**raw)
    except Exception as exc:
        import structlog

        structlog.get_logger(__name__).error(
            "presence_settings_invalid",
            raw_keys=list(raw.keys()),
            error=str(exc),
            action="falling back to defaults — fix this org's config JSONB",
        )
        return DEFAULT_PRESENCE_SETTINGS


def get_bug_reject_threshold(org_config: dict | None) -> int:
    """Return the open-bug count that triggers auto-rejection from testing.

    Thin wrapper so callers don't need to construct QAAutomationSettings.
    """
    return get_qa_settings(org_config).bug_reject_threshold


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


def get_jira_settings(org_config: dict | None) -> JiraSettings:
    """Resolve Jira connection settings from an organization config dict.

    Accepts ``None`` / missing / partial ``jira`` sections and fills in
    the shipped defaults (all empty strings). A fresh org with no jira
    section simply returns ``JiraSettings()`` with ``is_connected = False``.

    The ``api_token`` is stored encrypted via ``encrypt_secret()`` and
    decrypted here so callers receive a ready-to-use token.

    Args:
        org_config: The raw ``organization.config`` JSONB dict, or None.

    Returns:
        A ``JiraSettings`` with all fields populated (token decrypted).
    """
    raw = dict((org_config or {}).get("jira") or {})
    if raw.get("api_token"):
        import contextlib

        from app.core.encryption import decrypt_secret

        with contextlib.suppress(Exception):
            raw["api_token"] = decrypt_secret(raw["api_token"])
    return JiraSettings(**raw)
