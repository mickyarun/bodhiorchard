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
 * Typed error codes emitted by the AI agent runner when a Claude
 * subprocess terminates abnormally (max turns exhausted, timeout,
 * binary missing, etc.).
 *
 * Mirrors the backend ``ClaudeErrorCode`` enum in
 * ``backend/app/services/claude_errors.py`` — keep the string values in
 * lockstep. The ``error_code`` field on ``JobStatusRead`` carries one
 * of these values when an AI job fails; the frontend uses the code to
 * render rich UI (router-link to settings, role-aware CTAs) instead of
 * the raw fallback message.
 */

export const AGENT_ERROR_CODES = {
  MAX_TURNS: 'max_turns',
  TIMEOUT: 'timeout',
  BINARY_MISSING: 'binary_missing',
  UNKNOWN: 'unknown',
} as const

export type AgentErrorCode = (typeof AGENT_ERROR_CODES)[keyof typeof AGENT_ERROR_CODES]

/** Vue Router path to the page that lets admins edit per-skill ``max_turns``. */
const SETTINGS_AGENT_PROMPTS_ROUTE = '/settings/agent-prompts'

export interface FriendlyAgentError {
  /** Headline copy that summarises what went wrong, in plain English. */
  headline: string
  /** Vue Router route to the settings page that can fix this, if any. */
  settingsRoute: string | null
  /** True when the user can self-serve via settings (admins only). */
  suggestSettings: boolean
  /** True when contacting an admin is the appropriate next step. */
  suggestContactAdmin: boolean
}

const HEADLINES: Record<AgentErrorCode, string> = {
  [AGENT_ERROR_CODES.MAX_TURNS]:
    'The AI agent reached its maximum turns limit.',
  [AGENT_ERROR_CODES.TIMEOUT]:
    'The AI agent timed out before it could finish.',
  [AGENT_ERROR_CODES.BINARY_MISSING]:
    'The Claude CLI is not installed on this server.',
  [AGENT_ERROR_CODES.UNKNOWN]:
    'The AI agent failed unexpectedly.',
}

const GENERIC_FALLBACK_HEADLINE = 'The AI agent failed.'

export function isAgentErrorCode(value: unknown): value is AgentErrorCode {
  return (
    value === AGENT_ERROR_CODES.MAX_TURNS
    || value === AGENT_ERROR_CODES.TIMEOUT
    || value === AGENT_ERROR_CODES.BINARY_MISSING
    || value === AGENT_ERROR_CODES.UNKNOWN
  )
}

/**
 * Translate a ``(code, fallbackMessage)`` pair from a failed AI job
 * into a structured object the UI can render. ``MAX_TURNS`` is the
 * only category today where the user can self-serve via settings —
 * other categories suggest contacting an admin.
 */
export function friendlyAgentError(
  code: string | null | undefined,
  fallbackMessage: string | null | undefined,
): FriendlyAgentError {
  if (isAgentErrorCode(code)) {
    const headline = HEADLINES[code]
    return {
      headline,
      settingsRoute: code === AGENT_ERROR_CODES.MAX_TURNS ? SETTINGS_AGENT_PROMPTS_ROUTE : null,
      suggestSettings: code === AGENT_ERROR_CODES.MAX_TURNS,
      suggestContactAdmin: true,
    }
  }
  return {
    headline: fallbackMessage || GENERIC_FALLBACK_HEADLINE,
    settingsRoute: null,
    suggestSettings: false,
    suggestContactAdmin: true,
  }
}
