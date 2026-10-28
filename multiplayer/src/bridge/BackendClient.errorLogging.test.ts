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
 * A failed backend call is logged, and the error's text is not trusted: a
 * JSON parse error quotes the body the backend (or whatever answered on its
 * address) sent, a network error can quote a URL. Each log call must use a
 * constant format string and pass the error only as one sanitised field, so
 * no backend text can start a new log line or be read as a format string.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { OrgRoomState } from "../schema/OrgRoomState"
import { OrgRoom } from "../rooms/OrgRoom"
import {
  fetchOrgSnapshot,
  postBacklashInvite,
  postMinigameResults,
  postRaceInvite,
  postRaceResults,
  verifyUserToken,
} from "./BackendClient"

const FORGED_BODY = "not json\n[OrgRoom] Created org=forged\u2028"
const RAW_LINE_BREAKS = /[\n\r\u2028]/
const fetchMock = vi.fn()

/** Backend calls that parse the response body, with a payload each accepts. */
const PARSING_CALLS: Array<[string, () => Promise<unknown>]> = [
  ["fetchOrgSnapshot", () => fetchOrgSnapshot("org")],
  ["postMinigameResults", () => postMinigameResults({} as never)],
  ["postBacklashInvite", () => postBacklashInvite({} as never)],
  ["verifyUserToken", () => verifyUserToken("jwt", "org")],
]
/** Every backend call that logs its failure. */
const CALLS: Array<[string, () => Promise<unknown>]> = [
  ...PARSING_CALLS,
  ["postRaceInvite", () => postRaceInvite({} as never)],
  ["postRaceResults", () => postRaceResults({} as never)],
]
/** How the forged body reads once escaped: whole, or as the parse error quotes it. */
const ESCAPED_BODY = "not json\\n[OrgRoom] Created org=forged\\u2028"
const ESCAPED_EXCERPT = "not json\\n[O"

/** The single logged call, checked for a constant format and sanitised fields. */
function expectSanitisedLog(spy: ReturnType<typeof vi.spyOn>, escaped = ESCAPED_BODY): void {
  expect(spy).toHaveBeenCalledTimes(1)
  const [format, ...args] = spy.mock.calls[0] as unknown[]
  expect(String(format)).not.toContain("not json")
  expect(String(format)).toContain("%s")
  for (const arg of args) {
    expect(typeof arg).toBe("string")
    expect(String(arg)).not.toMatch(RAW_LINE_BREAKS)
  }
  expect(args.join(" ")).toContain(escaped)
}

let warnSpy: ReturnType<typeof vi.spyOn>
let errorSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal("fetch", fetchMock)
  warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined)
  errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined)
  vi.spyOn(console, "log").mockImplementation(() => undefined)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe.each(PARSING_CALLS)("%s parse failure logging", (_name, call) => {
  it("logs a body that does not parse as one sanitised field", async () => {
    fetchMock.mockResolvedValue(new Response(FORGED_BODY, { status: 200 }))

    await call()

    expectSanitisedLog(warnSpy, ESCAPED_EXCERPT)
  })
})

describe.each(CALLS)("%s network failure logging", (_name, call) => {
  it("logs a network error as one sanitised field", async () => {
    fetchMock.mockRejectedValue(new TypeError(`fetch failed: ${FORGED_BODY}`))

    await call()

    expectSanitisedLog(warnSpy)
  })
})

describe("OrgRoom snapshot load failure logging", () => {
  it("logs the error as one sanitised field", async () => {
    fetchMock.mockResolvedValue(Response.json({ members: [], repos: [] }))
    const room = new OrgRoom()
    room.setState(new OrgRoomState())
    room.state.orgId = "org"
    vi.spyOn(room as unknown as { loadSnapshot(): void }, "loadSnapshot").mockImplementation(() => {
      throw new Error(FORGED_BODY)
    })

    await (room as unknown as { loadInitialSnapshot(): Promise<void> }).loadInitialSnapshot()

    expectSanitisedLog(errorSpy)
    room.clock.clear()
  })
})
