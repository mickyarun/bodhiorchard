// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
