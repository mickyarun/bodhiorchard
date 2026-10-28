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
 * Pure request/compare helpers for the AI provider settings: what counts
 * as an unsaved edit, the PATCH /v1/settings/claude body and the
 * POST /v1/settings/claude/test body.
 */

/** The saved choice, as GET/PATCH /v1/settings/claude return it. */
export interface SavedSettings {
  provider: string
  auth_mode: string
  has_api_key: boolean
  base_url: string | null
  model: string | null
  thinking: boolean
}

/** The choice on screen. ``credential`` is the secret typed, if any. */
export interface AiProviderEdits {
  provider: string
  authMode: string
  baseUrl: string
  model: string
  thinking: boolean
  credential: string
}

export function hasUnsavedEdits(saved: SavedSettings | null, edits: AiProviderEdits): boolean {
  if (!saved) return false
  return (
    edits.provider !== saved.provider
    || edits.authMode !== saved.auth_mode
    || edits.baseUrl.trim() !== (saved.base_url ?? '')
    || edits.model !== (saved.model ?? '')
    || edits.thinking !== saved.thinking
    || edits.credential.trim().length > 0
  )
}

/** A typed secret goes out as the OAuth token or the API key, by auth mode. */
export function buildSavePayload(edits: AiProviderEdits, requiresSecret: boolean): Record<string, unknown> {
  const secret = edits.credential.trim()
  const sendSecret = requiresSecret && secret.length > 0
  return {
    provider: edits.provider,
    auth_mode: edits.authMode,
    // Always sent: the backend clears whichever the provider ignores.
    base_url: edits.baseUrl.trim(),
    model: edits.model,
    thinking: edits.thinking,
    ...(sendSecret && edits.authMode === 'subscription' ? { oauth_token: secret } : {}),
    ...(sendSecret && edits.authMode !== 'subscription' ? { api_key: secret } : {}),
  }
}

/** Test the address on screen, not the last saved one. */
export function testRequestBody(
  requiresBaseUrl: boolean,
  edits: Pick<AiProviderEdits, 'baseUrl' | 'model' | 'thinking'>,
): Record<string, unknown> | null {
  return requiresBaseUrl
    ? { base_url: edits.baseUrl.trim() || undefined, model: edits.model || undefined, thinking: edits.thinking }
    : null
}
