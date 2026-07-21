// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

import { describe, expect, it } from "vitest"
import { parseBacklashCreateMessage } from "./OrgBacklashHandler"

describe("parseBacklashCreateMessage", () => {
  it("accepts exactly one non-empty opponent id", () => {
    expect(parseBacklashCreateMessage({ invitedUserId: "user-2" })).toEqual({
      invitedUserId: "user-2",
    })
  })

  it.each([null, undefined, "user-2", [], 42])("rejects non-object input %j", (input) => {
    expect(parseBacklashCreateMessage(input)).toBeNull()
  })

  it.each([
    {},
    { invitedUserId: "" },
    { invitedUserId: 123 },
    { invitedUserId: "x".repeat(65) },
  ])("rejects malformed opponent payload %#", (input) => {
    expect(parseBacklashCreateMessage(input)).toBeNull()
  })
})
