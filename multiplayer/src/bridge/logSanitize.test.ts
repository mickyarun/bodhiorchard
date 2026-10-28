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

/** `safeLog`: the single sanitiser for user-controlled values in log lines. */
import { describe, expect, it } from "vitest"
import { safeLog } from "./logSanitize"

describe("safeLog", () => {
  it("passes plain identifiers through unchanged", () => {
    expect(safeLog("org-1234_abcd")).toBe("org-1234_abcd")
  })

  it("escapes CR and LF so a value cannot forge a new log line", () => {
    const out = safeLog("legit\r\n[BridgeEndpoint] deliver type=fake")
    expect(out).toBe("legit\\r\\n[BridgeEndpoint] deliver type=fake")
    expect(out).not.toMatch(/[\r\n]/)
  })

  it("escapes other control characters and quotes", () => {
    expect(safeLog('tab\there "quoted" \u0000')).toBe('tab\\there \\"quoted\\" \\u0000')
  })

  it("renders null and undefined as visible placeholders", () => {
    expect(safeLog(null)).toBe("<null>")
    expect(safeLog(undefined)).toBe("<undefined>")
  })

  it("stringifies non-string values", () => {
    expect(safeLog(42)).toBe("42")
    expect(safeLog(false)).toBe("false")
    expect(safeLog({ toString: () => "line1\nline2" })).toBe("line1\\nline2")
  })

  it("caps the value at 500 characters before escaping", () => {
    expect(safeLog("x".repeat(10_000))).toHaveLength(500)
  })

  it("keeps the cap when the 500th character is a newline", () => {
    const value = `${"y".repeat(499)}\n${"z".repeat(100)}`
    const out = safeLog(value)
    expect(out.endsWith("\\n")).toBe(true)
    expect(out).not.toContain("z")
  })

  it("handles an empty string", () => {
    expect(safeLog("")).toBe("")
  })
})
