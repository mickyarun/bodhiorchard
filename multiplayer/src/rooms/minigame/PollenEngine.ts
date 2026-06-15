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
  GAME_SECONDS,
  type Mote,
  SPAWN_EVERY_S,
  isMoteAlive,
  spawnMote,
} from "../../../../shared/minigames/pollen"
import type { MinigameEngine, MinigameHost } from "./MinigameEngine"

const SPAWN_EVERY_MS = SPAWN_EVERY_S * 1000
const DURATION_MS = GAME_SECONDS * 1000

/**
 * Server-authoritative Pollen Pop. The server owns the mote field: it spawns
 * motes (its RNG) on a fixed tick and streams them; the client renders but
 * never invents motes. A pop is validated against the server's live set at the
 * server's clock, so a mote that never existed or already drifted off-screen
 * can't be popped. Score is the count of valid pops.
 */
export class PollenEngine implements MinigameEngine {
  private readonly motes = new Map<number, Mote>()
  private nextId = 1
  private score = 0
  private startMs = 0
  private lastSpawnMs = 0

  constructor(
    private readonly rng: () => number = Math.random,
    private readonly now: () => number = () => Date.now(),
  ) {}

  start(host: MinigameHost): void {
    this.startMs = this.now()
    this.lastSpawnMs = this.startMs
    host.notify("pollen_start", { durationMs: DURATION_MS })
  }

  tick(host: MinigameHost, nowMs: number): void {
    if (nowMs - this.startMs >= DURATION_MS) {
      host.finish()
      return
    }
    while (nowMs - this.lastSpawnMs >= SPAWN_EVERY_MS) {
      this.lastSpawnMs += SPAWN_EVERY_MS
      const mote = spawnMote(this.nextId++, nowMs, this.rng)
      this.motes.set(mote.id, mote)
      host.notify("pollen_spawn", mote)
    }
    for (const [id, mote] of this.motes) {
      if (!isMoteAlive(mote, nowMs)) {
        this.motes.delete(id)
        host.notify("pollen_despawn", { id })
      }
    }
  }

  input(host: MinigameHost, type: string, payload: unknown): void {
    if (type !== "pop") return
    const id = readId(payload)
    if (id === null) return
    const mote = this.motes.get(id)
    if (!mote || !isMoteAlive(mote, this.now())) return
    this.motes.delete(id)
    this.score += 1
    host.state.score = this.score
    host.notify("pollen_popped", { id, score: this.score })
  }

  finalScore(): number {
    return this.score
  }
}

function readId(payload: unknown): number | null {
  if (typeof payload !== "object" || payload === null) return null
  const id = (payload as { id?: unknown }).id
  return typeof id === "number" && Number.isInteger(id) ? id : null
}
