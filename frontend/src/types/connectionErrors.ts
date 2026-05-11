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
 * Typed error codes returned by ``PATCH /v1/settings/connections``
 * when GitHub-App credentials fail synchronous validation.
 *
 * Mirrors backend constants in
 * ``backend/app/services/github_app_slug.py`` — keep the strings in
 * lockstep. The credentials form maps these to localised messages so
 * we never parse free-text from the backend.
 */

export const CONNECTION_ERROR_CODES = {
  GITHUB_APP_CREDENTIALS_INVALID: 'github_app_credentials_invalid',
  GITHUB_APP_NOT_FOUND: 'github_app_not_found',
  GITHUB_UNREACHABLE: 'github_unreachable',
} as const

export type ConnectionErrorCode =
  (typeof CONNECTION_ERROR_CODES)[keyof typeof CONNECTION_ERROR_CODES]

export interface ConnectionErrorPayload {
  error: ConnectionErrorCode | string
  message: string
}

const FRIENDLY_MESSAGES: Record<ConnectionErrorCode, string> = {
  [CONNECTION_ERROR_CODES.GITHUB_APP_CREDENTIALS_INVALID]:
    'GitHub rejected the credentials. Double-check the App ID and private key.',
  [CONNECTION_ERROR_CODES.GITHUB_APP_NOT_FOUND]:
    'GitHub could not find a GitHub App with this App ID.',
  [CONNECTION_ERROR_CODES.GITHUB_UNREACHABLE]:
    'Could not reach GitHub right now. Check your network and try again.',
}

/** Type guard for backend error envelopes that may pre-date Phase J. */
export function isConnectionErrorCode(value: unknown): value is ConnectionErrorCode {
  return (
    value === CONNECTION_ERROR_CODES.GITHUB_APP_CREDENTIALS_INVALID
    || value === CONNECTION_ERROR_CODES.GITHUB_APP_NOT_FOUND
    || value === CONNECTION_ERROR_CODES.GITHUB_UNREACHABLE
  )
}

/**
 * Map a typed connection error code to a user-facing message. Falls
 * back to the backend-supplied message (or a generic catch-all) when
 * the code is unknown — keeps us forward-compatible with future error
 * codes the backend may add.
 */
export function friendlyConnectionErrorMessage(
  payload: ConnectionErrorPayload | null | undefined,
): string {
  if (!payload) return 'Save failed. Please try again.'
  if (isConnectionErrorCode(payload.error)) {
    return FRIENDLY_MESSAGES[payload.error]
  }
  return payload.message || 'Save failed. Please try again.'
}
