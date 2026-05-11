// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

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
