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
import { parseRaceCreateMessage, raceRacerCount } from "./OrgRaceHandler"
import { resolveBotCount } from "./RaceRoomHelpers"
import { MAX_RACERS } from "../../../shared/race/RaceConstants"

describe("parseRaceCreateMessage", () => {
  it("accepts a valid 100m invite (trackShape defaults to straight)", () => {
    const msg = parseRaceCreateMessage({
      invitedUserIds: ["user-a", "user-b"],
      distanceM: 100,
    })
    expect(msg).toEqual({
      invitedUserIds: ["user-a", "user-b"],
      distanceM: 100,
      trackShape: "straight",
      botCount: 0,
    })
  })

  it("accepts an explicit circuit trackShape", () => {
    const msg = parseRaceCreateMessage({
      invitedUserIds: ["user-a"],
      distanceM: 200,
      trackShape: "circuit",
    })
    expect(msg?.trackShape).toBe("circuit")
  })

  it("rejects trackShapes outside the allowed set", () => {
    expect(
      parseRaceCreateMessage({ invitedUserIds: ["a"], distanceM: 100, trackShape: "oval" }),
    ).toBeNull()
    expect(
      parseRaceCreateMessage({ invitedUserIds: ["a"], distanceM: 100, trackShape: 1 }),
    ).toBeNull()
  })

  it("accepts a valid 200m invite", () => {
    const msg = parseRaceCreateMessage({
      invitedUserIds: ["user-a"],
      distanceM: 200,
    })
    expect(msg?.distanceM).toBe(200)
  })

  it("rejects distances outside the allowed set", () => {
    expect(parseRaceCreateMessage({ invitedUserIds: ["a"], distanceM: 150 })).toBeNull()
    expect(parseRaceCreateMessage({ invitedUserIds: ["a"], distanceM: 0 })).toBeNull()
  })

  it("rejects non-array invitees", () => {
    expect(parseRaceCreateMessage({ invitedUserIds: "a,b", distanceM: 100 })).toBeNull()
  })

  it("rejects empty-string invitee ids", () => {
    expect(parseRaceCreateMessage({ invitedUserIds: ["ok", ""], distanceM: 100 })).toBeNull()
  })

  it("rejects non-string invitee entries", () => {
    expect(parseRaceCreateMessage({ invitedUserIds: ["ok", 42], distanceM: 100 })).toBeNull()
  })

  it("rejects non-object input", () => {
    expect(parseRaceCreateMessage(null)).toBeNull()
    expect(parseRaceCreateMessage("hi")).toBeNull()
    expect(parseRaceCreateMessage(undefined)).toBeNull()
  })

  it("accepts an integer botCount and defaults a missing one to 0", () => {
    expect(
      parseRaceCreateMessage({ invitedUserIds: [], distanceM: 100, botCount: 3 })?.botCount,
    ).toBe(3)
    expect(
      parseRaceCreateMessage({ invitedUserIds: ["a"], distanceM: 100 })?.botCount,
    ).toBe(0)
  })

  it("rejects non-integer botCount values", () => {
    expect(
      parseRaceCreateMessage({ invitedUserIds: [], distanceM: 100, botCount: "3" }),
    ).toBeNull()
    expect(
      parseRaceCreateMessage({ invitedUserIds: [], distanceM: 100, botCount: 1.5 }),
    ).toBeNull()
    expect(
      parseRaceCreateMessage({ invitedUserIds: [], distanceM: 100, botCount: NaN }),
    ).toBeNull()
  })
})

describe("raceRacerCount occupancy cap", () => {
  // The create handler rejects with "too_many_invitees" when this exceeds
  // MAX_RACERS. Bots are resolved through the same prod-gate + clamp the
  // room uses, so the cap must count them.
  const fits = (invitees: number, rawBots: number, isProd: boolean): boolean =>
    raceRacerCount(invitees, resolveBotCount(rawBots, isProd)) <= MAX_RACERS

  it("counts host + invitees + dev bots toward the cap", () => {
    // host(1) + 1 invitee + 7 bots = 9 ≤ 10 → fits.
    expect(fits(1, 7, false)).toBe(true)
    // host(1) + 3 invitees + 7 bots = 11 > 10 → rejected.
    expect(fits(3, 7, false)).toBe(false)
  })

  it("accepts a full grid exactly at MAX_RACERS", () => {
    // host(1) + 9 bots = 10.
    expect(fits(0, MAX_RACERS - 1, false)).toBe(true)
    // one more human tips it over.
    expect(fits(1, MAX_RACERS - 1, false)).toBe(false)
  })

  it("ignores bots in production so only host + invitees count", () => {
    // A crafted prod payload asking for 9 bots still seats 0 bots, so a
    // host + 9 invitees race fits and a 10-invitee race does not.
    expect(fits(MAX_RACERS - 1, 9, true)).toBe(true)
    expect(fits(MAX_RACERS, 9, true)).toBe(false)
  })
})
