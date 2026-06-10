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
import {
  assertRaceCreateOptions,
  buildRacerState,
  buildRaceResultsPayload,
  copyRacerToSchema,
  placingToSchema,
} from "./RaceRoomHelpers"
import { PlacingState } from "../schema/PlacingState"
import { RacerState } from "../schema/RacerState"
import { checkFinish, type Racer } from "../../../shared/race/RacePhysics"
import type { Placing } from "../../../shared/race/types"

const ALLOWED = [100, 200] as const

describe("assertRaceCreateOptions", () => {
  it("accepts a well-formed options object", () => {
    const opts = assertRaceCreateOptions(
      {
        orgId: "org-1",
        hostUserId: "user-1",
        hostName: "Alice",
        distanceM: 100,
        invitedUserIds: ["user-2", "user-3"],
      },
      ALLOWED,
    )
    expect(opts).toEqual({
      orgId: "org-1",
      hostUserId: "user-1",
      hostName: "Alice",
      distanceM: 100,
      invitedUserIds: ["user-2", "user-3"],
    })
  })

  it("filters invalid entries out of invitedUserIds", () => {
    const opts = assertRaceCreateOptions(
      {
        orgId: "o",
        hostUserId: "h",
        hostName: "n",
        distanceM: 100,
        invitedUserIds: ["good", "", null, 42, "also-good"],
      },
      ALLOWED,
    )
    expect(opts.invitedUserIds).toEqual(["good", "also-good"])
  })

  it("throws on missing required fields", () => {
    expect(() =>
      assertRaceCreateOptions({ hostUserId: "h", hostName: "n", distanceM: 100 }, ALLOWED),
    ).toThrow(/orgId/)
  })

  it("throws on distance outside the allowed set", () => {
    expect(() =>
      assertRaceCreateOptions(
        { orgId: "o", hostUserId: "h", hostName: "n", distanceM: 150 },
        ALLOWED,
      ),
    ).toThrow(/distanceM/)
  })

  it("throws on non-object input", () => {
    expect(() => assertRaceCreateOptions("bad", ALLOWED)).toThrow(/object/)
    expect(() => assertRaceCreateOptions(null, ALLOWED)).toThrow(/object/)
  })
})

describe("buildRacerState", () => {
  it("creates a RacerState with lane index applied", () => {
    const r = buildRacerState(
      { userId: "u", name: "Alice", characterModel: "kaykit:barbarian" },
      2,
    )
    expect(r).not.toBeNull()
    expect(r?.userId).toBe("u")
    expect(r?.id).toBe("u")
    expect(r?.name).toBe("Alice")
    expect(r?.characterModel).toBe("kaykit:barbarian")
    expect(r?.laneIndex).toBe(2)
  })

  it("returns null on missing userId / name", () => {
    expect(buildRacerState({ userId: "u" }, 0)).toBeNull()
    expect(buildRacerState({ name: "n" }, 0)).toBeNull()
    expect(buildRacerState(null, 0)).toBeNull()
  })
})

function makeFinishedRacer(id: string, finishTimeMs: number, positionM = 100): Racer {
  return {
    id,
    positionM,
    velocityMps: 0,
    finished: true,
    finishTimeMs,
    isMoving: false,
    sprintUntilMs: 0,
    staminaPct: 1,
  }
}

function makeDnfRacer(id: string, positionM: number): Racer {
  return {
    id,
    positionM,
    velocityMps: 0,
    finished: false,
    finishTimeMs: 0,
    isMoving: false,
    sprintUntilMs: 0,
    staminaPct: 1,
  }
}

describe("checkFinish (shared/race)", () => {
  it("emits exactly one Placing per Racer for a 4-finisher race", () => {
    // The contract that prevents the "only winner appears on the
    // leaderboard" symptom — checkFinish must never drop a racer.
    const racers: Racer[] = [
      makeFinishedRacer("u1", 14_500),
      makeFinishedRacer("u2", 14_580),
      makeFinishedRacer("u3", 14_660),
      makeFinishedRacer("u4", 14_740),
    ]
    const placings = checkFinish(racers, false)
    expect(placings).toHaveLength(4)
    expect(placings.map((p) => p.racerId)).toEqual(["u1", "u2", "u3", "u4"])
    expect(placings.map((p) => p.place)).toEqual([1, 2, 3, 4])
    expect(placings.every((p) => p.finished)).toBe(true)
  })

  it("breaks same-tick finishTimeMs ties by post-tick positionM (further wins)", () => {
    // When racers cross the line in the same 50 ms tick, finishTimeMs
    // is identical and the second sort key — positionM — picks the
    // racer who travelled further inside that tick. Names are ordered
    // such that an id-only tiebreak would invert the expected ranking,
    // so this case actually exercises rule #2 from checkFinish's
    // docstring rather than falling through to rule #3.
    const racers: Racer[] = [
      makeFinishedRacer("uA", 14_640, 100.1),
      makeFinishedRacer("uB", 14_640, 100.4),
      makeFinishedRacer("uC", 14_640, 100.2),
    ]
    const placings = checkFinish(racers, false)
    expect(placings.map((p) => p.racerId)).toEqual(["uB", "uC", "uA"])
  })

  it("falls back to ascending id only when finishTimeMs and positionM both tie", () => {
    // Both keys identical — rule #3 in the docstring. The previous test
    // explicitly avoids this branch so this one pins it independently.
    const racers: Racer[] = [
      makeFinishedRacer("u3", 14_640),
      makeFinishedRacer("u1", 14_640),
      makeFinishedRacer("u2", 14_640),
    ]
    const placings = checkFinish(racers, false)
    expect(placings.map((p) => p.racerId)).toEqual(["u1", "u2", "u3"])
  })

  it("places DNFs after finishers, ranked by distance descending", () => {
    const racers: Racer[] = [
      makeFinishedRacer("winner", 14_500),
      makeDnfRacer("dnf-far", 80),
      makeDnfRacer("dnf-near", 40),
    ]
    // `timeoutFired` is currently a no-op inside checkFinish; pass false
    // here so the test doesn't imply it gates any behaviour. Removing
    // the dead parameter is tracked for a follow-up checkpoint.
    const placings = checkFinish(racers, false)
    expect(placings).toHaveLength(3)
    expect(placings[0]).toMatchObject({ racerId: "winner", finished: true, place: 1 })
    expect(placings[1]).toMatchObject({ racerId: "dnf-far", finished: false, place: 2 })
    expect(placings[2]).toMatchObject({ racerId: "dnf-near", finished: false, place: 3 })
  })
})

describe("placingToSchema", () => {
  it("maps every Placing field onto the schema instance", () => {
    const p: Placing = {
      racerId: "user-7",
      place: 3,
      finished: true,
      finishTimeMs: 15_240,
      distanceM: 100,
    }
    const schema = placingToSchema(p)
    expect(schema).toBeInstanceOf(PlacingState)
    expect(schema.racerId).toBe("user-7")
    expect(schema.place).toBe(3)
    expect(schema.finished).toBe(true)
    expect(schema.finishTimeMs).toBe(15_240)
    expect(schema.distanceM).toBe(100)
  })
})

function makePlacing(over: Partial<PlacingState> = {}): PlacingState {
  const s = new PlacingState()
  s.racerId = "racer-x"
  s.place = 1
  s.finished = true
  s.finishTimeMs = 14_000
  s.distanceM = 100
  Object.assign(s, over)
  return s
}

describe("buildRaceResultsPayload", () => {
  const header = {
    roomId: "race-test",
    orgId: "org-1",
    hostUserId: "host-1",
    distanceM: 100,
  }

  it("emits one payload row per placing for a 4-finisher race", () => {
    // Direct guard for the reported "only winner appears on the leaderboard"
    // symptom — all four placings must survive the payload-building step.
    const placings = [
      makePlacing({ racerId: "u1", place: 1, finishTimeMs: 14_500, distanceM: 100 }),
      makePlacing({ racerId: "u2", place: 2, finishTimeMs: 14_580, distanceM: 100 }),
      makePlacing({ racerId: "u3", place: 3, finishTimeMs: 14_660, distanceM: 100 }),
      makePlacing({ racerId: "u4", place: 4, finishTimeMs: 14_740, distanceM: 100 }),
    ]
    const payload = buildRaceResultsPayload(header, placings)
    expect(payload).not.toBeNull()
    expect(payload?.placings.map((p) => p.userId)).toEqual(["u1", "u2", "u3", "u4"])
    expect(payload?.placings.every((p) => p.finished)).toBe(true)
    expect(payload?.placings.map((p) => p.finishTimeMs)).toEqual([
      14_500,
      14_580,
      14_660,
      14_740,
    ])
    expect(payload?.placings.every((p) => p.distanceM === 100)).toBe(true)
  })

  it("includes DNFs with finishTimeMs=null alongside finishers", () => {
    const placings = [
      makePlacing({ racerId: "winner", place: 1, finishTimeMs: 14_500, distanceM: 100 }),
      makePlacing({
        racerId: "dnf-a",
        place: 2,
        finished: false,
        finishTimeMs: 0,
        distanceM: 72.5,
      }),
      makePlacing({
        racerId: "dnf-b",
        place: 3,
        finished: false,
        finishTimeMs: 0,
        distanceM: 55,
      }),
    ]
    const payload = buildRaceResultsPayload(header, placings)
    expect(payload).not.toBeNull()
    expect(payload?.placings).toHaveLength(3)
    const dnfA = payload?.placings.find((p) => p.userId === "dnf-a")
    expect(dnfA?.finishTimeMs).toBeNull()
    expect(dnfA?.finished).toBe(false)
    expect(dnfA?.distanceMReached).toBe(72.5)
  })

  it("returns null on an empty placings iterable (room disposed pre-finish)", () => {
    expect(buildRaceResultsPayload(header, [])).toBeNull()
  })

  it("returns null when no racer finished (timeout DNF-only round)", () => {
    const placings = [
      makePlacing({
        racerId: "dnf-1",
        place: 1,
        finished: false,
        finishTimeMs: 0,
        distanceM: 80,
      }),
      makePlacing({
        racerId: "dnf-2",
        place: 2,
        finished: false,
        finishTimeMs: 0,
        distanceM: 65,
      }),
    ]
    expect(buildRaceResultsPayload(header, placings)).toBeNull()
  })

  it("propagates distanceM from the header onto every row", () => {
    const placings = [
      makePlacing({ racerId: "u1", finishTimeMs: 26_300, distanceM: 100 }),
      makePlacing({ racerId: "u2", place: 2, finishTimeMs: 27_100, distanceM: 100 }),
    ]
    const payload = buildRaceResultsPayload({ ...header, distanceM: 200 }, placings)
    expect(payload?.distanceM).toBe(200)
    expect(payload?.placings.every((p) => p.distanceM === 200)).toBe(true)
  })
})

describe("copyRacerToSchema", () => {
  it("copies mutable fields without touching identity", () => {
    const schema = new RacerState()
    schema.id = "fixed-id"
    schema.userId = "fixed-user"
    schema.name = "fixed-name"

    const phys: Racer = {
      id: "fixed-user",
      positionM: 42.5,
      velocityMps: 6.1,
      finished: true,
      finishTimeMs: 12_340,
      isMoving: true,
      sprintUntilMs: 13_000,
      staminaPct: 0.42,
    }

    copyRacerToSchema(phys, schema)
    expect(schema.id).toBe("fixed-id")
    expect(schema.userId).toBe("fixed-user")
    expect(schema.name).toBe("fixed-name")
    expect(schema.positionM).toBe(42.5)
    expect(schema.velocityMps).toBe(6.1)
    expect(schema.finished).toBe(true)
    expect(schema.finishTimeMs).toBe(12_340)
    expect(schema.isMoving).toBe(true)
    expect(schema.sprintUntilMs).toBe(13_000)
    expect(schema.staminaPct).toBeCloseTo(0.42, 5)
  })
})
