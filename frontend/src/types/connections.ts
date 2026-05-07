// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Settings → Connections shared types.
 *
 * Mirrors the backend ``GitHubAppStatus`` enum from
 * ``backend/app/schemas/settings.py``. Values must match byte-for-byte —
 * the wire format is the lowercase string (``"not_configured"`` …) and
 * Pydantic's ``StrEnum`` serialises by value.
 */

export const GITHUB_APP_STATUS = {
  NOT_CONFIGURED: 'not_configured',
  AWAITING_INSTALL: 'awaiting_install',
  READY: 'ready',
} as const

export type GitHubAppStatus = (typeof GITHUB_APP_STATUS)[keyof typeof GITHUB_APP_STATUS]

/** Type guard for backend responses that may pre-date the status field. */
export function isGitHubAppStatus(value: unknown): value is GitHubAppStatus {
  return (
    value === GITHUB_APP_STATUS.NOT_CONFIGURED ||
    value === GITHUB_APP_STATUS.AWAITING_INSTALL ||
    value === GITHUB_APP_STATUS.READY
  )
}
