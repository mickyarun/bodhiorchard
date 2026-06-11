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

import { describe, it, expect } from "vitest"
import { driveBots } from "./RaceBotDriver"
import { makeRacer, tick, type Racer } from "../../../shared/race/RacePhysics"
import { TICK_MS } from "../../../shared/race/RaceConstants"

const TRACK_LENGTH_M = 100

/** Run a full simulated race: driveBots + physics tick, like RaceRoom.simStep. */
function simulateRace(
  botCount: number,
  maxMs: number,
): { racers: Racer[]; knockedDownEver: Set<string>; finishOrder: string[] } {
  const racers: Racer[] = []
  for (let n = 1; n <= botCount; n++) racers.push(makeRacer(`bot-${n}`))
  const knockedDownEver = new Set<string>()
  const finishOrder: string[] = []
  const finished = new Set<string>()

  for (let elapsed = TICK_MS; elapsed <= maxMs; elapsed += TICK_MS) {
    driveBots(racers, elapsed, TICK_MS, TRACK_LENGTH_M)
    tick(racers, TICK_MS, elapsed, TRACK_LENGTH_M)
    for (const r of racers) {
      if (r.knockdownUntilMs > 0) knockedDownEver.add(r.id)
      if (r.finished && !finished.has(r.id)) {
        finished.add(r.id)
        finishOrder.push(r.id)
      }
    }
    if (finished.size === racers.length) break
  }
  return { racers, knockedDownEver, finishOrder }
}

describe("driveBots determinism", () => {
  it("identical inputs produce identical races, tap for tap", () => {
    const a = simulateRace(7, 120_000)
    const b = simulateRace(7, 120_000)
    expect(b.finishOrder).toEqual(a.finishOrder)
    for (let i = 0; i < a.racers.length; i++) {
      expect(b.racers[i].positionM).toBe(a.racers[i].positionM)
      expect(b.racers[i].finishTimeMs).toBe(a.racers[i].finishTimeMs)
      expect(b.racers[i].sprintUntilMs).toBe(a.racers[i].sprintUntilMs)
      expect(b.racers[i].lastJumpMs).toBe(a.racers[i].lastJumpMs)
    }
    expect(b.knockedDownEver).toEqual(a.knockedDownEver)
  })
})

describe("driveBots behaviour", () => {
  it("every bot finishes well before the running timeout", () => {
    const { racers } = simulateRace(7, 120_000)
    for (const r of racers) {
      expect(r.finished).toBe(true)
      expect(r.finishTimeMs).toBeLessThan(90_000)
    }
  })

  it("per-bot cadences spread the field — no two finish times equal", () => {
    const { racers } = simulateRace(7, 120_000)
    const times = racers.map((r) => r.finishTimeMs)
    expect(new Set(times).size).toBe(times.length)
  })

  it("some bots clip hurdles (knockdown variety) and some clear cleanly", () => {
    const { knockedDownEver, racers } = simulateRace(7, 120_000)
    expect(knockedDownEver.size).toBeGreaterThan(0)
    expect(knockedDownEver.size).toBeLessThan(racers.length)
  })

  it("bots attempt jumps (lastJumpMs advances past its initial backdate)", () => {
    const { racers } = simulateRace(3, 120_000)
    for (const r of racers) {
      expect(r.lastJumpMs).toBeGreaterThan(0)
    }
  })
})
