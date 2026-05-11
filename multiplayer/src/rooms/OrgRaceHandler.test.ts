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
import { parseRaceCreateMessage } from "./OrgRaceHandler"

describe("parseRaceCreateMessage", () => {
  it("accepts a valid 100m invite", () => {
    const msg = parseRaceCreateMessage({
      invitedUserIds: ["user-a", "user-b"],
      distanceM: 100,
    })
    expect(msg).toEqual({
      invitedUserIds: ["user-a", "user-b"],
      distanceM: 100,
    })
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
})
