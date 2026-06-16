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

import { describe, expect, it } from "vitest"
import type { MinigameRoomState } from "../../schema/MinigameRoomState"
import type { MinigameHost } from "./MinigameEngine"
import { FireflyEngine } from "./FireflyEngine"
import { FishingEngine } from "./FishingEngine"
import { PollenEngine } from "./PollenEngine"

interface SentMessage {
  type: string
  message: unknown
}

function makeHost(): {
  host: MinigameHost
  sent: SentMessage[]
  state: { score: number; round: number }
  finished: () => boolean
} {
  const sent: SentMessage[] = []
  let finished = false
  const state = { score: 0, round: 0 }
  const host: MinigameHost = {
    state: state as unknown as MinigameRoomState,
    notify: (type, message) => sent.push({ type, message }),
    scheduleAfter: (_ms, fn) => fn(), // run synchronously in tests
    finish: () => {
      finished = true
    },
  }
  return { host, sent, state, finished: () => finished }
}

const last = (sent: SentMessage[], type: string): SentMessage | undefined =>
  [...sent].reverse().find((s) => s.type === type)

describe("FireflyEngine", () => {
  it("computes the score server-side from validated taps", () => {
    // rng → 0 always: first pad 'emerald', then no-repeat pool picks index 0.
    const engine = new FireflyEngine(() => 0)
    const { host, sent, state, finished } = makeHost()
    engine.start(host)

    const seq1 = last(sent, "firefly_sequence")?.message as { sequence: string[]; level: number }
    expect(seq1.level).toBe(1)
    expect(seq1.sequence).toEqual(["emerald"])

    // Clear level 1 → score 1, level 2 streams.
    engine.input(host, "tap", { padId: "emerald" })
    expect(state.score).toBe(1)
    const seq2 = last(sent, "firefly_sequence")?.message as { sequence: string[] }
    expect(seq2.sequence).toEqual(["emerald", "amber"])

    // Clear level 2 → score 2.
    engine.input(host, "tap", { padId: "emerald" })
    engine.input(host, "tap", { padId: "amber" })
    expect(state.score).toBe(2)

    // A wrong tap ends the game at the last cleared level.
    engine.input(host, "tap", { padId: "rose" })
    expect(finished()).toBe(true)
    expect(engine.finalScore()).toBe(2)
  })

  it("ignores invalid pad payloads", () => {
    const engine = new FireflyEngine(() => 0)
    const { host, finished } = makeHost()
    engine.start(host)
    engine.input(host, "tap", { padId: "not-a-pad" })
    engine.input(host, "tap", {})
    engine.input(host, "nonsense", { padId: "emerald" })
    expect(finished()).toBe(false)
  })
})

describe("FishingEngine", () => {
  it("scores hooks server-side and finishes after five casts", () => {
    // zoneStart = 0.08 + 0.5*(0.84-0.16) = 0.42 → centre 0.5. rng 0.5 also gives
    // phase = 1.0, so sin(1·π) = 0 → elapsed 0 → bobber at 0.5 → bullseye (10).
    const engine = new FishingEngine(() => 0.5, () => 1000)
    const { host, state, finished } = makeHost()
    engine.start(host)
    for (let i = 0; i < 5; i++) {
      // A client-sent "score" in the payload is ignored — the server computes it.
      engine.input(host, "hook", { score: 999 })
    }
    expect(state.score).toBe(50)
    expect(finished()).toBe(true)
    expect(engine.finalScore()).toBe(50)
    // A sixth hook after the game is over does nothing.
    engine.input(host, "hook", {})
    expect(engine.finalScore()).toBe(50)
  })

  it("scores from the client's in-cast time, immune to server latency", () => {
    let clock = 0
    // zone centred at 0.5 (rng 0.5 → zoneStart 0.42).
    const engine = new FishingEngine(() => 0.5, () => clock)
    const { host, sent } = makeHost()
    engine.start(host) // cast 0, castStartMs = 0
    // 5s elapsed server-side (latency), but the client hooked at the very start
    // (bobber at 0.5 = bullseye). Scoring at the server's own 5000ms clock would
    // put the bobber well off-centre (a worse band); using the client's reported
    // moment it's a bullseye.
    clock = 5000
    engine.input(host, "hook", { elapsedMs: 0 })
    const r = last(sent, "fishing_result")?.message as { points: number }
    expect(r.points).toBe(10)
  })

  it("clamps a client-reported time to the server-measured window", () => {
    let clock = 0
    const engine = new FishingEngine(() => 0.5, () => clock)
    const { host, sent } = makeHost()
    engine.start(host) // castStartMs = 0
    clock = 0 // ~no server time elapsed → a hook can't be claimed from later
    engine.input(host, "hook", { elapsedMs: 999999 })
    const r = last(sent, "fishing_result")?.message as { marker: number }
    expect(r.marker).toBeCloseTo(0.5, 6) // clamped to t=0, not the claimed future
  })
})

describe("PollenEngine", () => {
  it("validates pops against the server's live mote field", () => {
    let clock = 0
    const engine = new PollenEngine(() => 0.5, () => clock)
    const { host, sent, state, finished } = makeHost()
    engine.start(host)

    // Tick past the first spawn interval → exactly one mote spawned.
    clock = 600
    engine.tick(host, 600)
    const spawn = last(sent, "pollen_spawn")?.message as { id: number }
    expect(spawn).toBeTruthy()

    // A valid pop of a live mote scores once; a repeat or unknown id does not.
    clock = 650
    engine.input(host, "pop", { id: spawn.id })
    expect(state.score).toBe(1)
    engine.input(host, "pop", { id: spawn.id }) // already popped
    engine.input(host, "pop", { id: 9999 }) // never existed
    expect(state.score).toBe(1)

    // Reaching the duration finishes the game.
    clock = 25000
    engine.tick(host, 25000)
    expect(finished()).toBe(true)
    expect(engine.finalScore()).toBe(1)
  })
})
