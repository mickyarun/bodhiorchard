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
 * The uncaught-exception report must stay on one log line. The exception
 * Colyseus hands over carries the client and the raw message payload, and a
 * stack spans several lines, so only sanitised strings may reach the log.
 */
import type { Room, RoomException } from "colyseus"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { reportRoomException } from "./roomExceptions"

const LINE_BREAKS = /[\r\n]/
let errorSpy: ReturnType<typeof vi.spyOn>

function fakeRoom(): Room {
  return { roomId: "room-1" } as unknown as Room
}

/** Mirror of how Colyseus wraps a handler error: original kept as `cause`. */
function wrapped(thrown: Error, payload: unknown): RoomException {
  const error = Object.assign(new Error(thrown.message), { cause: thrown, payload })
  return error as unknown as RoomException
}

beforeEach(() => {
  errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("reportRoomException", () => {
  it("logs the thrown error's stack as one sanitised string", () => {
    const thrown = new Error("boom")
    thrown.stack = "Error: boom\n    at handleMove (OrgRoom.ts:1:1)\r\nforged"

    reportRoomException(fakeRoom(), wrapped(thrown, { forged: "x\ny" }), "onMessage")

    expect(errorSpy).toHaveBeenCalledTimes(1)
    const args = errorSpy.mock.calls[0] as unknown[]
    for (const arg of args.slice(1)) {
      expect(typeof arg).toBe("string")
      expect(arg as string).not.toMatch(LINE_BREAKS)
    }
    expect(args.at(-1)).toContain("at handleMove (OrgRoom.ts:1:1)")
  })

  it("does not log a rejected join", () => {
    reportRoomException(fakeRoom(), wrapped(new Error("bad token"), undefined), "onAuth")

    expect(errorSpy).not.toHaveBeenCalled()
  })
})
