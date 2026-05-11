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
 * Stateful phrase cycler for legacy (non-server-driven) agent characters.
 *
 * Phrase DATA lives in `@shared/agents/AgentPhrases` so the multiplayer
 * server and client can't drift. This module only owns the per-skill
 * cursor that the frontend needs when advancing phrases locally — the
 * server tracks its own cursors per-agent in `AgentActivitySim`.
 */

import { PHRASES, DEFAULT_PHRASES } from '@shared/agents/AgentPhrases'

const indices = new Map<string, number>()

/** Get the next working phrase for a skill, cycling through the list. */
export function getNextPhrase(skillSlug: string): string {
  const phrases = PHRASES[skillSlug] ?? DEFAULT_PHRASES
  const idx = (indices.get(skillSlug) ?? 0) % phrases.length
  indices.set(skillSlug, idx + 1)
  return phrases[idx]
}
