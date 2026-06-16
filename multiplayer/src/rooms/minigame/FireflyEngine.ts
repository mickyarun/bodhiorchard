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

import {
  PADS,
  type PadId,
  extendSequence,
  flashDurationForLevel,
  isRoundComplete,
  matchStep,
} from "../../../../shared/minigames/firefly"
import type { MinigameEngine, MinigameHost } from "./MinigameEngine"

const PAD_IDS = new Set<string>(PADS.map((p) => p.id))
/** Pause after clearing a level so the client can show the level-up shimmer
 *  before the next (longer, faster) sequence streams. */
const LEVELUP_PAUSE_MS = 620
/** Minimum gap between accepted taps. Humans tap a sequence at a few per second;
 *  this only bites a script replaying the streamed answer at machine speed. */
const TAP_MIN_GAP_MS = 80

/**
 * Server-authoritative Firefly Follow. The server generates the sequence (with
 * its own RNG), streams it for the client to render, and validates each tap
 * against its own sequence — the score is the number of levels cleared, decided
 * entirely server-side.
 *
 * The sequence has to be sent (the player must watch it), so a script can read
 * it off the wire and replay it. Two server-side guards make that cost real-time
 * play rather than an instant sweep: the first tap of a round can't land before
 * the sequence has finished flashing (you can't repeat what you haven't seen),
 * and taps can't arrive faster than a human can press.
 */
export class FireflyEngine implements MinigameEngine {
  private sequence: PadId[] = []
  private inputIndex = 0
  private level = 0
  private cleared = 0
  /** False during the level-up pause — rejects taps until the next round streams. */
  private accepting = false
  private roundStartMs = 0
  private minFirstTapMs = 0
  private lastTapMs = Number.NEGATIVE_INFINITY

  constructor(
    private readonly rng: () => number = Math.random,
    private readonly now: () => number = () => Date.now(),
  ) {}

  start(host: MinigameHost): void {
    this.beginRound(host, 1, [])
  }

  input(host: MinigameHost, type: string, payload: unknown): void {
    if (type !== "tap" || !this.accepting) return
    const padId = readPad(payload)
    if (padId === null) return
    const now = this.now()
    // Can't repeat a sequence before it's finished flashing, and can't tap
    // faster than a human — both drop an instant bot replaying the streamed
    // answer (dropped, not counted wrong, so a stray double-tap isn't punished).
    if (this.inputIndex === 0 && now - this.roundStartMs < this.minFirstTapMs) return
    if (now - this.lastTapMs < TAP_MIN_GAP_MS) return
    this.lastTapMs = now

    if (matchStep(this.sequence, this.inputIndex, padId) === "wrong") {
      this.accepting = false
      host.notify("firefly_result", { result: "wrong", padId })
      host.finish()
      return
    }

    this.inputIndex += 1
    if (isRoundComplete(this.sequence, this.inputIndex)) {
      this.accepting = false
      this.cleared = this.level
      host.state.score = this.cleared
      host.notify("firefly_result", { result: "levelup", level: this.cleared })
      // Hold the shimmer before the next round streams — paced by the server.
      const next = this.level + 1
      const prev = this.sequence
      host.scheduleAfter(LEVELUP_PAUSE_MS, () => this.beginRound(host, next, prev))
    } else {
      host.notify("firefly_result", { result: "ok", index: this.inputIndex })
    }
  }

  finalScore(): number {
    return this.cleared
  }

  private beginRound(host: MinigameHost, level: number, prev: PadId[]): void {
    this.level = level
    this.sequence = extendSequence(prev, this.rng)
    this.inputIndex = 0
    this.accepting = true
    const flashMs = flashDurationForLevel(level)
    this.roundStartMs = this.now()
    // A conservative lower bound on how long the client takes to flash the whole
    // sequence (it adds gaps too, so the real display is longer) — the player
    // can't have watched it before this, so a correct tap before it is a bot.
    this.minFirstTapMs = this.sequence.length * flashMs
    this.lastTapMs = Number.NEGATIVE_INFINITY
    host.state.round = level
    host.notify("firefly_sequence", { level, sequence: this.sequence, flashMs })
  }
}

function readPad(payload: unknown): PadId | null {
  if (typeof payload !== "object" || payload === null) return null
  const padId = (payload as { padId?: unknown }).padId
  return typeof padId === "string" && PAD_IDS.has(padId) ? (padId as PadId) : null
}
