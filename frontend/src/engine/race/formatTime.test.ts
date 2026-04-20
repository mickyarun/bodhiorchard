// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
