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
import { CASTS_PER_LEVEL, FISHING_LIVES } from "../../../../shared/minigames/fishing"
import { MAX_CONCURRENT_MOTES, quotaForLevel } from "../../../../shared/minigames/pollen"
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
  state: { score: number; round: number; lives: number }
  finished: () => boolean
} {
  const sent: SentMessage[] = []
  let finished = false
  const state = { score: 0, round: 0, lives: 0 }
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
    let clock = 0
    const engine = new FireflyEngine(() => 0, () => clock)
    const { host, sent, state, finished } = makeHost()
    engine.start(host)

    const seq1 = last(sent, "firefly_sequence")?.message as {
      sequence: string[]
      level: number
      flashMs: number
    }
    expect(seq1.level).toBe(1)
    expect(seq1.sequence).toEqual(["emerald"])

    // Clear level 1 → score 1, level 2 streams. Wait out the sequence display
    // first, or the tap is dropped as too-fast-to-have-watched-it.
    clock += seq1.sequence.length * seq1.flashMs + 50
    engine.input(host, "tap", { padId: "emerald" })
    expect(state.score).toBe(1)
    const seq2 = last(sent, "firefly_sequence")?.message as { sequence: string[]; flashMs: number }
    expect(seq2.sequence).toEqual(["emerald", "amber"])

    // Clear level 2 → score 2 (space the two taps past the rate cap).
    clock += seq2.sequence.length * seq2.flashMs + 50
    engine.input(host, "tap", { padId: "emerald" })
    clock += 100
    engine.input(host, "tap", { padId: "amber" })
    expect(state.score).toBe(2)

    // A wrong tap ends the game at the last cleared level.
    const seq3 = last(sent, "firefly_sequence")?.message as { sequence: string[]; flashMs: number }
    clock += seq3.sequence.length * seq3.flashMs + 50
    engine.input(host, "tap", { padId: "rose" })
    expect(finished()).toBe(true)
    expect(engine.finalScore()).toBe(2)
  })

  it("drops an instant replay of the streamed sequence", () => {
    let clock = 0
    const engine = new FireflyEngine(() => 0, () => clock)
    const { host, sent, state, finished } = makeHost()
    engine.start(host)
    const seq = last(sent, "firefly_sequence")?.message as { sequence: string[] }
    // A bot echoes the answer the instant it arrives (clock barely moved) → the
    // reaction floor drops it: no score, game still running.
    clock += 10
    engine.input(host, "tap", { padId: seq.sequence[0] })
    expect(state.score).toBe(0)
    expect(finished()).toBe(false)
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
  it("scores hits server-side and steps the level up every CASTS_PER_LEVEL casts", () => {
    // zoneStart = 0.08 + 0.5*(0.84-0.16) = 0.42 → centre 0.5. rng 0.5 also gives
    // phase = 1.0, so sin(1·π) = 0 → elapsed 0 → bobber at 0.5 → bullseye (10).
    // Every hook hits, so lives never drop and the level can climb.
    const engine = new FishingEngine(() => 0.5, () => 1000)
    const { host, state } = makeHost()
    engine.start(host)
    expect(state.round).toBe(1)
    for (let i = 0; i < CASTS_PER_LEVEL; i++) {
      // A client-sent "score" in the payload is ignored — the server computes it.
      engine.input(host, "hook", { elapsedMs: 0, score: 999 })
    }
    expect(state.score).toBe(CASTS_PER_LEVEL * 10)
    expect(state.lives).toBe(FISHING_LIVES) // no misses → no lives lost
    expect(state.round).toBe(2) // stepped up after CASTS_PER_LEVEL casts
  })

  it("loses a life on a missed hook and ends the run at zero lives", () => {
    // rng 0 → zoneStart 0.08 (centre 0.16), phase 0 → bobber at elapsed 0 is
    // 0.5: well outside the zone, so every hook misses and bleeds a life.
    const engine = new FishingEngine(() => 0, () => 0)
    const { host, state, finished } = makeHost()
    engine.start(host)
    for (let i = 0; i < FISHING_LIVES; i++) {
      expect(finished()).toBe(false)
      engine.input(host, "hook", { elapsedMs: 0 })
    }
    expect(state.lives).toBe(0)
    expect(finished()).toBe(true)
    expect(engine.finalScore()).toBe(0)
    // A hook after game over does nothing.
    engine.input(host, "hook", { elapsedMs: 0 })
    expect(engine.finalScore()).toBe(0)
  })

  it("honours the client's in-cast time within the latency grace", () => {
    let clock = 0
    // zone centred at 0.5 (rng 0.5 → zoneStart 0.42).
    const engine = new FishingEngine(() => 0.5, () => clock)
    const { host, sent } = makeHost()
    engine.start(host) // cast 0, castStartMs = 0
    // 250ms of network latency, but the client hooked at the very start (bobber
    // at 0.5 = bullseye). The reported time agrees with the server's measure
    // within the grace, so it's honoured — lag doesn't punish a correct tap.
    clock = 250
    engine.input(host, "hook", { elapsedMs: 0 })
    const r = last(sent, "fishing_result")?.message as { points: number }
    expect(r.points).toBe(10)
  })

  it("rejects a hooked time banked far from when the hook arrived", () => {
    let clock = 0
    const engine = new FishingEngine(() => 0.5, () => clock)
    const { host, sent } = makeHost()
    engine.start(host) // castStartMs = 0; elapsed 0 would be a bullseye
    // A bot waits 5s, then claims the perfect elapsed (0). That's far outside the
    // latency grace, so the claim is dropped and the hook is scored at the real
    // arrival time — not the banked bullseye.
    clock = 5000
    engine.input(host, "hook", { elapsedMs: 0 })
    const r = last(sent, "fishing_result")?.message as { points: number }
    expect(r.points).toBeLessThan(10)
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
  it("validates pops and advances a level once the quota is cleared", () => {
    let clock = 0
    const engine = new PollenEngine(() => 0.5, () => clock)
    const { host, state } = makeHost()
    engine.start(host)
    expect(state.round).toBe(1)

    // rng 0.5 → neutral jitter, so a mote (id = i) spawns each 600ms interval.
    // Tick to spawn it, wait a human reaction beat (clears the reaction floor),
    // then pop it — clearing level 1's quota.
    const quota = quotaForLevel(1)
    for (let i = 1; i <= quota; i++) {
      clock += 600
      engine.tick(host, clock)
      clock += 130
      engine.input(host, "pop", { id: i })
    }
    expect(state.score).toBe(quota)
    expect(state.round).toBe(2) // quota cleared → level up

    // A repeat or unknown id does not score.
    engine.input(host, "pop", { id: 1 })
    engine.input(host, "pop", { id: 9999 })
    expect(state.score).toBe(quota)
  })

  it("drops pops below human reaction or click speed", () => {
    let clock = 0
    const engine = new PollenEngine(() => 0.5, () => clock)
    const { host, state } = makeHost()
    engine.start(host)
    clock = 600
    engine.tick(host, 600) // mote id 1 spawns at 600
    clock = 1200
    engine.tick(host, 1200) // mote id 2 spawns at 1200

    // Reaction floor: id 2 popped 40ms after it spawned → dropped as a bot.
    clock = 1240
    engine.input(host, "pop", { id: 2 })
    expect(state.score).toBe(0)

    // id 1 is 660ms old → a human-plausible pop scores.
    clock = 1260
    engine.input(host, "pop", { id: 1 })
    expect(state.score).toBe(1)

    // Rate cap: id 2 now clears the reaction floor (125ms old) but the pop lands
    // 65ms after the last scored one → above human click speed → dropped.
    clock = 1325
    engine.input(host, "pop", { id: 2 })
    expect(state.score).toBe(1)

    // 80ms after the last scored pop → within human speed → scored.
    clock = 1340
    engine.input(host, "pop", { id: 2 })
    expect(state.score).toBe(2)
  })

  it("loses a life when escapes blow the budget, ending at zero lives", () => {
    let clock = 0
    const engine = new PollenEngine(() => 0.5, () => clock)
    const { host, state, finished } = makeHost()
    engine.start(host)
    // Never pop: motes spawn and drift off the top. Each escape eats the level
    // budget; enough escapes drain every life and end the run.
    for (let t = 0; t < 1000 && !finished(); t++) {
      clock += 500
      engine.tick(host, clock)
    }
    expect(finished()).toBe(true)
    expect(state.lives).toBe(0)
  })

  it("never lets more than MAX_CONCURRENT_MOTES live at once", () => {
    let clock = 0
    // rng=0 → slow-rising, long-lived motes that pile up fast, so the cap is
    // the only thing keeping the arena from flooding. Bounded below the first
    // escape so the run is still live and density is purely cap-limited.
    const engine = new PollenEngine(() => 0, () => clock)
    const { host, sent } = makeHost()
    engine.start(host)

    let live = 0
    let maxLive = 0
    for (clock = 100; clock <= 12000; clock += 100) {
      const before = sent.length
      engine.tick(host, clock)
      for (let i = before; i < sent.length; i++) {
        if (sent[i].type === "pollen_spawn") live += 1
        else if (sent[i].type === "pollen_despawn") live -= 1
      }
      // The cap holds every tick — never a transient overshoot.
      expect(live).toBeLessThanOrEqual(MAX_CONCURRENT_MOTES)
      maxLive = Math.max(maxLive, live)
    }

    expect(maxLive).toBe(MAX_CONCURRENT_MOTES) // and it does fill to the cap
  })
})
