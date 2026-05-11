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
 * Agent stack-index calculation.
 *
 * When multiple agents share the same repo tree, each needs a stable
 * slot so they fan out instead of overlapping. Both server
 * (`AgentActivitySim`) and client-legacy (`AgentCharacterSystem`) need
 * the same count — "how many agents are already at this tree?" — at
 * the moment a new agent spawns. This helper is that count.
 *
 * The caller is responsible for freezing the result onto the spawning
 * agent so sibling completions don't shift an already-placed agent.
 */

/** Minimum shape required to determine an entry's current repo. */
export interface StackEntry {
  repoNames: string[]
  currentRepoIndex: number
}

/**
 * Count entries currently targeting `targetRepo`.
 *
 * Callers may pass a richer entry type (the generic `E extends StackEntry`
 * preserves their full shape so the `isActive` predicate can close over
 * caller-only fields like `key`). Example — client passing
 * `e => this.characters.has(e.key)` where `key` is not on StackEntry.
 *
 * @param entries    Live entries excluding the spawning agent — callers
 *                   must add the new entry AFTER computing its index.
 * @param targetRepo Repo the new agent will spawn at.
 * @param isActive   Optional filter (e.g. client's "character still alive"
 *                   guard). Server does not use this.
 */
export function countAgentsAtRepo<E extends StackEntry>(
  entries: Iterable<E>,
  targetRepo: string,
  isActive?: (entry: E) => boolean,
): number {
  let count = 0
  for (const entry of entries) {
    if (entry.repoNames[entry.currentRepoIndex] !== targetRepo) continue
    if (isActive && !isActive(entry)) continue
    count++
  }
  return count
}
