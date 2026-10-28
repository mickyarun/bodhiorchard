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
 * Join options are client-controlled and bridge payloads carry backend values
 * that came from users (display names, org settings), so none of them may
 * start a new log line or repaint the terminal. Each forged character below
 * is one a log viewer or terminal treats specially: CR, LF, the Unicode line
 * and paragraph separators, and the ESC that opens an ANSI sequence.
 */
import type { Client } from "colyseus"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { registerOrgRoom, unregisterOrgRoom } from "../bridge/BridgeEndpoint"
import { buildPresenceConfig } from "../sim/PresenceConfig"
import { CafeteriaRoom } from "./CafeteriaRoom"
import { CoffeeBarRoom } from "./CoffeeBarRoom"
import { HouseRoom } from "./HouseRoom"
import type { OrgRoom } from "./OrgRoom"
import type { JoinCredentials, JoinIdentity } from "../auth/verifyJoin"
import { createRaceRoom } from "../testing/raceRoom"

const CR = "\r"
const LF = "\n"
const LINE_SEPARATOR = String.fromCharCode(0x2028)
const PARAGRAPH_SEPARATOR = String.fromCharCode(0x2029)
const ESC = String.fromCharCode(0x1b)
const RAW_SPECIALS = [CR, LF, LINE_SEPARATOR, PARAGRAPH_SEPARATOR, ESC]
const FORGED_NAME =
  `bob${CR}${LF}[HouseRoom] admin joined${LINE_SEPARATOR}x${PARAGRAPH_SEPARATOR}y` +
  `${ESC}[31mred${ESC}[0m`

const ORG = "org-a"

/** The join hooks every shared room exposes. */
interface JoinableRoom {
  onAuth(client: Client, options: JoinCredentials): Promise<JoinIdentity>
  onJoin(client: Client, options: JoinCredentials, auth?: JoinIdentity): void
}

let logSpy: ReturnType<typeof vi.spyOn>
let warnSpy: ReturnType<typeof vi.spyOn>
let errorSpy: ReturnType<typeof vi.spyOn>

function joinClient(): Client {
  return { sessionId: "s-bob", userData: undefined, send: vi.fn() } as unknown as Client
}

/** The single line on `spy` mentioning the forged name. */
function loggedLine(spy: ReturnType<typeof vi.spyOn> = logSpy): string {
  const lines = spy.mock.calls.map((call: unknown[]) => call.map(String).join(" "))
  const matching = lines.filter((line: string) => line.includes("bob"))
  expect(matching).toHaveLength(1)
  return matching[0]
}

function expectSanitised(line: string): void {
  for (const ch of RAW_SPECIALS) expect(line).not.toContain(ch)
  expect(line).toContain("bob\\r\\n[HouseRoom] admin joined\\u2028x\\u2029y")
  expect(line).toContain("\\u001b[31mred")
}

beforeEach(() => {
  logSpy = vi.spyOn(console, "log").mockImplementation(() => undefined)
  warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined)
  errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("join log lines escape a forged display name", () => {
  // The name a room logs on join is the stored one the backend returns from
  // verify-token, and members choose their own display names.
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({ valid: true, user_id: "bob", org_id: ORG, name: FORGED_NAME }),
      ),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  /** Run a join the way Colyseus does: onAuth, then onJoin with its result. */
  async function verifiedJoin(room: JoinableRoom, client: Client): Promise<void> {
    const options = { token: "jwt-bob", orgId: ORG }
    room.onJoin(client, options, await room.onAuth(client, options))
  }

  it("HouseRoom join", async () => {
    const room = new HouseRoom()
    room.onCreate({ orgId: ORG, ownerId: "alice" })
    await verifiedJoin(room, joinClient())
    expectSanitised(loggedLine())
  })

  it("HouseRoom leave", async () => {
    const room = new HouseRoom()
    room.onCreate({ orgId: ORG, ownerId: "alice" })
    await verifiedJoin(room, joinClient())
    logSpy.mockClear()
    room.onLeave(joinClient())
    expectSanitised(loggedLine())
  })

  it("CoffeeBarRoom join", async () => {
    const room = new CoffeeBarRoom()
    room.onCreate({ orgId: ORG })
    await verifiedJoin(room, joinClient())
    expectSanitised(loggedLine())
    room.setSimulationInterval(undefined)
  })

  it("CafeteriaRoom join", async () => {
    const room = new CafeteriaRoom()
    room.onCreate({ orgId: ORG })
    await verifiedJoin(room, joinClient())
    expectSanitised(loggedLine())
    room.setSimulationInterval(undefined)
  })

  it("RaceRoom join", async () => {
    const room = createRaceRoom({ orgId: ORG })
    await verifiedJoin(room, joinClient())
    expectSanitised(loggedLine())
    room.clock.clear()
  })
})

describe("bridge registry log lines escape a forged org id", () => {
  it("register and unregister", () => {
    const fakeRoom = {} as OrgRoom
    registerOrgRoom(FORGED_NAME, fakeRoom)
    expectSanitised(loggedLine())
    logSpy.mockClear()
    unregisterOrgRoom(FORGED_NAME)
    expectSanitised(loggedLine())
  })
})

describe("presence settings log lines escape forged backend values", () => {
  const settings = {
    autoModeEnabled: true,
    workingDays: ["mon" as const],
    workingHoursStart: "09:00",
    workingHoursEnd: "17:00",
    timezone: null,
  }

  it("an invalid timezone", () => {
    buildPresenceConfig({ ...settings, timezone: FORGED_NAME })
    expectSanitised(loggedLine(warnSpy))
  })

  it("unmappable working days", () => {
    const workingDays = [FORGED_NAME] as unknown as typeof settings.workingDays
    buildPresenceConfig({ ...settings, workingDays })
    const line = loggedLine(errorSpy)
    for (const ch of RAW_SPECIALS) expect(line).not.toContain(ch)
  })
})
