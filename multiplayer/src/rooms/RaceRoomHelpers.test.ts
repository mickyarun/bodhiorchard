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
  copyRacerToSchema,
} from "./RaceRoomHelpers"
import { RacerState } from "../schema/RacerState"
import type { Racer } from "../../../shared/race/RacePhysics"

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
  })
})
