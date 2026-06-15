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

import { CASTS, bobberPositionAt, randomZoneStart, scoreForHook } from "../../../../shared/minigames/fishing"
import type { MinigameEngine, MinigameHost } from "./MinigameEngine"

/** Clamp ceiling for server-measured cast elapsed — a stalled tab can't run the
 *  bobber phase off to a wild value. */
const MAX_CAST_MS = 20000
/** Pause after a hook so the client can show the catch/miss feedback before the
 *  next cast begins (the next `fishing_cast` is what clears it). */
const RESULT_PAUSE_MS = 700

/**
 * Server-authoritative Lake Fishing. The server owns the strike zone (its RNG)
 * and the cast clock. A hook carries no score: the server recomputes where the
 * bobber really was — using its OWN measured elapsed, so the client can't claim
 * a perfect hook — and scores it. The small latency penalty is the trade-off
 * for not trusting client-reported timing.
 */
export class FishingEngine implements MinigameEngine {
  private cast = 0
  private score = 0
  private zoneStart = 0
  private castStartMs = 0
  /** True only while a cast is live — rejects stray hooks during the inter-cast
   *  pause (and any malicious double-hook). */
  private canHook = false

  constructor(
    private readonly rng: () => number = Math.random,
    private readonly now: () => number = () => Date.now(),
  ) {}

  start(host: MinigameHost): void {
    this.cast = 0
    this.score = 0
    this.beginCast(host)
  }

  input(host: MinigameHost, type: string, _payload: unknown): void {
    if (type !== "hook" || !this.canHook) return
    this.canHook = false
    const elapsed = Math.min(MAX_CAST_MS, Math.max(0, this.now() - this.castStartMs))
    const marker = bobberPositionAt(elapsed, this.cast)
    const points = scoreForHook(marker, this.zoneStart)
    this.score += points
    host.state.score = this.score
    host.notify("fishing_result", { cast: this.cast, points, marker })

    this.cast += 1
    // Hold the result on screen before advancing (or finishing), so the catch
    // feedback is visible — the server paces this, not the client.
    if (this.cast >= CASTS) {
      host.scheduleAfter(RESULT_PAUSE_MS, () => host.finish())
    } else {
      host.scheduleAfter(RESULT_PAUSE_MS, () => this.beginCast(host))
    }
  }

  finalScore(): number {
    return this.score
  }

  private beginCast(host: MinigameHost): void {
    this.zoneStart = randomZoneStart(this.rng)
    this.castStartMs = this.now()
    this.canHook = true
    host.state.round = this.cast + 1
    host.notify("fishing_cast", { cast: this.cast, zoneStart: this.zoneStart })
  }
}
