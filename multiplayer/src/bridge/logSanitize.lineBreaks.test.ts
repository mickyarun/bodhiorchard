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

/**
 * `safeLog` must escape every character a log viewer may treat as a line
 * break, including the ones `JSON.stringify` leaves untouched, and every log
 * site that prints a network-supplied id must go through it.
 */
import { afterEach, describe, expect, it, vi } from "vitest"
import { fireBacklashDispose, registerBacklashSummaryHooks } from "./BacklashRegistry"
import { safeLog } from "./logSanitize"
import { fireRaceDispose, fireRacePhase, registerRaceHooks } from "./RaceRegistry"

const NEL = String.fromCharCode(0x85)
const LINE_SEPARATOR = String.fromCharCode(0x2028)
const PARAGRAPH_SEPARATOR = String.fromCharCode(0x2029)

describe("safeLog Unicode line breaks", () => {
  it.each([
    ["NEL", NEL, "\\u0085"],
    ["line separator", LINE_SEPARATOR, "\\u2028"],
    ["paragraph separator", PARAGRAPH_SEPARATOR, "\\u2029"],
  ])("escapes the %s", (_label, ch, escaped) => {
    const out = safeLog(`repo${ch}[BridgeEndpoint] deliver type=forged`)
    expect(out).not.toContain(ch)
    expect(out).toBe(`repo${escaped}[BridgeEndpoint] deliver type=forged`)
  })

  it("still escapes CR and LF next to them", () => {
    expect(safeLog(`a\r\n${LINE_SEPARATOR}b`)).toBe("a\\r\\n\\u2028b")
  })

  it("leaves other non-ASCII text readable", () => {
    expect(safeLog("café 日本")).toBe("café 日本")
  })
})

describe("registry error logs", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("pass room ids through safeLog", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined)
    const roomId = `room${LINE_SEPARATOR}forged\nline`
    const fail = (): void => {
      throw new Error("hook failed")
    }
    registerRaceHooks(roomId, { onDispose: fail, onPhase: fail })
    registerBacklashSummaryHooks(roomId, { onDispose: fail, onPhase: fail, onViewers: fail })

    fireRacePhase(roomId, "running")
    fireRaceDispose(roomId)
    fireBacklashDispose(roomId)

    expect(errorSpy).toHaveBeenCalledTimes(3)
    const loggedIds = errorSpy.mock.calls.map((call) =>
      call.find((arg) => typeof arg === "string" && arg.startsWith("room")),
    )
    expect(loggedIds).toEqual(Array(3).fill(safeLog(roomId)))
  })
})
