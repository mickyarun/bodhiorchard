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

/**
 * Server-authoritative Firefly Follow. The server generates the sequence (with
 * its own RNG), streams it for the client to render, and validates each tap
 * against its own sequence — the score is the number of levels cleared, decided
 * entirely server-side.
 */
export class FireflyEngine implements MinigameEngine {
  private sequence: PadId[] = []
  private inputIndex = 0
  private level = 0
  private cleared = 0
  /** False during the level-up pause — rejects taps until the next round streams. */
  private accepting = false

  constructor(private readonly rng: () => number = Math.random) {}

  start(host: MinigameHost): void {
    this.beginRound(host, 1, [])
  }

  input(host: MinigameHost, type: string, payload: unknown): void {
    if (type !== "tap" || !this.accepting) return
    const padId = readPad(payload)
    if (padId === null) return

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
    host.state.round = level
    host.notify("firefly_sequence", {
      level,
      sequence: this.sequence,
      flashMs: flashDurationForLevel(level),
    })
  }
}

function readPad(payload: unknown): PadId | null {
  if (typeof payload !== "object" || payload === null) return null
  const padId = (payload as { padId?: unknown }).padId
  return typeof padId === "string" && PAD_IDS.has(padId) ? (padId as PadId) : null
}
