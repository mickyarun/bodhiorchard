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
 * Firefly Follow — pure game logic for the colour-sequence memory game.
 *
 * Framework-free and shared: the Colyseus server (authoritative) owns the
 * sequence and validates taps with these functions, while the client component
 * imports the same module to render. Keeping the rules here — not in the SFC —
 * is what lets the score be computed server-side. `rng` is injectable so both
 * the server (server-seeded RNG) and the tests stay deterministic.
 */

/** A pad's stable identity. Order here is the 2×2 board order. */
export type PadId = 'emerald' | 'amber' | 'rose' | 'sky'

export interface Pad {
  id: PadId
  /** Base (idle) colour — the lit/glow treatment lives in the component CSS. */
  color: string
  /** A position-stable glyph so the sequence is followable without relying on
   *  hue alone (colour-blind accessibility). */
  glyph: string
}

export const PADS: readonly Pad[] = [
  { id: 'emerald', color: '#2ecc8f', glyph: '✦' },
  { id: 'amber', color: '#f5b342', glyph: '●' },
  { id: 'rose', color: '#f06595', glyph: '◆' },
  { id: 'sky', color: '#4dabf7', glyph: '▲' },
] as const

const PAD_IDS: readonly PadId[] = PADS.map((p) => p.id)

/** Flash-duration bounds (milliseconds). Level 1 starts comfortably readable;
 *  the ramp bottoms out at the floor — below ~240ms distinct flashes stop being
 *  reliably trackable, which would turn the game into luck and flatten the
 *  leaderboard rather than spread it. */
export const START_FLASH_MS = 620
export const FLOOR_FLASH_MS = 240

/**
 * Per-level speed-up factor: each cleared level multiplies the flash duration
 * by this. A GEOMETRIC ramp, not a linear one — players perceive ratios, not
 * absolute differences (Weber–Fechner), so equal multiplicative steps read as
 * evenly-paced difficulty instead of a late-game lurch, and the curve stays
 * gentle across the opening rounds where new players are won or lost. At ~0.93
 * a 620ms flash reaches the 240ms floor around level 15 — late enough that
 * speed keeps separating skilled players through the competitive scoring band
 * before it caps.
 */
export const FLASH_DECAY_PER_LEVEL = 0.93

/**
 * Pick a pad id uniformly at random. `rng` is injectable so the server and
 * tests stay deterministic; it defaults to `Math.random`.
 */
export function randomPad(rng: () => number = Math.random): PadId {
  return PAD_IDS[Math.floor(rng() * PAD_IDS.length)]
}

/**
 * Return a new sequence with one fresh pad appended. Pure — never mutates the
 * input (the caller holds the canonical sequence).
 *
 * The new pad is never the same as the immediately-preceding one: on a 4-pad
 * board a back-to-back repeat of the same colour reads as a single box pulsing
 * rather than two distinct presses, which is unfair to track. Picking from the
 * other three pads keeps every consecutive flash visually unambiguous.
 */
export function extendSequence(seq: readonly PadId[], rng: () => number = Math.random): PadId[] {
  const prev = seq[seq.length - 1]
  if (prev === undefined) return [...seq, randomPad(rng)]
  const pool = PAD_IDS.filter((id) => id !== prev)
  return [...seq, pool[Math.floor(rng() * pool.length)]]
}

/**
 * Per-flash playback duration for a given level, in milliseconds — the
 * heartbeat of the game's difficulty. `level` is 1-based (level 1 is the
 * first, easiest round).
 *
 * A geometric decay clamped to a floor (see FLASH_DECAY_PER_LEVEL for the
 * rationale). By construction it equals START_FLASH_MS at level 1, is
 * monotonically non-increasing, and never drops below FLOOR_FLASH_MS.
 */
export function flashDurationForLevel(level: number): number {
  const raw = START_FLASH_MS * FLASH_DECAY_PER_LEVEL ** (level - 1)
  return Math.max(FLOOR_FLASH_MS, Math.round(raw))
}

/**
 * Check a single player tap against the expected sequence.
 *
 * `index` is how many correct taps the player has already made this round, so
 * `seq[index]` is the pad they must hit next.
 */
export function matchStep(seq: readonly PadId[], index: number, padId: PadId): 'ok' | 'wrong' {
  return seq[index] === padId ? 'ok' : 'wrong'
}

/**
 * True once the player has correctly tapped the whole sequence for this round
 * (i.e. the number of correct taps equals the sequence length).
 */
export function isRoundComplete(seq: readonly PadId[], correctTaps: number): boolean {
  return correctTaps >= seq.length
}
