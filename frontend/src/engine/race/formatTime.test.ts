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
import { formatRaceTime } from "./formatTime"

describe("formatRaceTime", () => {
  it("returns '--' for zero or negative durations", () => {
    expect(formatRaceTime(0)).toBe("--")
    expect(formatRaceTime(-5)).toBe("--")
  })

  it("returns '--' for non-finite durations", () => {
    expect(formatRaceTime(NaN)).toBe("--")
    expect(formatRaceTime(Infinity)).toBe("--")
  })

  it("formats sub-second times with two fractional digits", () => {
    expect(formatRaceTime(120)).toBe("0.12 s")
    expect(formatRaceTime(9)).toBe("0.00 s") // truncation, not rounding
    expect(formatRaceTime(999)).toBe("0.99 s")
  })

  it("formats times under one minute with seconds", () => {
    expect(formatRaceTime(12_340)).toBe("12.34 s")
    expect(formatRaceTime(59_990)).toBe("59.99 s")
  })

  it("switches to m:ss.hh at one minute", () => {
    expect(formatRaceTime(60_000)).toBe("1:00.00")
    expect(formatRaceTime(83_450)).toBe("1:23.45")
    expect(formatRaceTime(3_599_990)).toBe("59:59.99")
  })

  it("switches to h:mm:ss.h at one hour", () => {
    expect(formatRaceTime(3_600_000)).toBe("1:00:00.0")
    expect(formatRaceTime(3_723_400)).toBe("1:02:03.4")
  })
})
