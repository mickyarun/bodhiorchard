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
 * Backend → Colyseus bridge endpoint: secret check, envelope validation and
 * routing to org rooms / room-scoped registries. Driven with fake Express
 * request/response objects; no HTTP server is started.
 */
import type { Request, Response } from "express"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { OrgRoom } from "../rooms/OrgRoom"
import { handleBridgePublish, registerOrgRoom, unregisterOrgRoom } from "./BridgeEndpoint"
import { fireRaceDispose, registerRaceHooks } from "./RaceRegistry"
import {
  registerBacklashDeclineHandler,
  unregisterBacklashDeclineHandler,
} from "./BacklashRegistry"

const SECRET = process.env.COLYSEUS_BRIDGE_SECRET ?? "dev-colyseus-bridge-secret"

interface FakeResponse {
  statusCode: number
  body: unknown
}

function call(headers: Record<string, string>, body: unknown): FakeResponse {
  const out: FakeResponse = { statusCode: 0, body: undefined }
  const req = {
    header: (name: string) => headers[name.toLowerCase()],
    body,
  } as unknown as Request
  const res = {
    status(code: number) {
      out.statusCode = code
      return this
    },
    json(payload: unknown) {
      out.body = payload
      return this
    },
  } as unknown as Response
  handleBridgePublish(req, res)
  return out
}

function authed(body: unknown): FakeResponse {
  return call({ "x-bridge-secret": SECRET }, body)
}

function fakeOrgRoom(impl?: (type: string, data: unknown) => void) {
  const handleBridgeEvent = vi.fn(impl ?? (() => undefined))
  return { room: { handleBridgeEvent } as unknown as OrgRoom, handleBridgeEvent }
}

/** Rooms registered by a test, released afterwards (only the holder can release a slot). */
const registered: Array<[string, OrgRoom]> = []

function register(orgId: string, room: OrgRoom): void {
  registerOrgRoom(orgId, room)
  registered.push([orgId, room])
}

let logSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  logSpy = vi.spyOn(console, "log").mockImplementation(() => undefined)
  vi.spyOn(console, "error").mockImplementation(() => undefined)
})

afterEach(() => {
  for (const [orgId, room] of registered.splice(0)) unregisterOrgRoom(orgId, room)
  fireRaceDispose("race-1")
  unregisterBacklashDeclineHandler("bl-1")
  vi.restoreAllMocks()
})

describe("bridge secret", () => {
  it("rejects a request without the secret header", () => {
    expect(call({}, { orgId: "org-a", type: "dev_activity", data: {} })).toEqual({
      statusCode: 401,
      body: { error: "invalid bridge secret" },
    })
  })

  it("rejects a wrong secret of the same length", () => {
    const wrong = "x".repeat(SECRET.length)
    expect(call({ "x-bridge-secret": wrong }, { orgId: "org-a", type: "t", data: {} }).statusCode)
      .toBe(401)
  })

  it("rejects a secret that only shares a prefix with the real one", () => {
    const longer = `${SECRET}-extra`
    expect(call({ "x-bridge-secret": longer }, { orgId: "org-a", type: "t", data: {} }).statusCode)
      .toBe(401)
  })
})

describe("envelope validation", () => {
  it("rejects a body without a type", () => {
    expect(authed({ orgId: "org-a", data: {} })).toEqual({
      statusCode: 400,
      body: { error: "missing type" },
    })
  })

  it("rejects an empty body", () => {
    expect(authed(undefined).statusCode).toBe(400)
  })

  it("rejects an envelope carrying both orgId and roomId", () => {
    const res = authed({ orgId: "org-a", roomId: "room-1", type: "t", data: {} })
    expect(res).toEqual({
      statusCode: 400,
      body: { error: "exactly one of orgId or roomId is required" },
    })
  })

  it("rejects an envelope carrying neither routing key", () => {
    expect(authed({ type: "t", data: {} }).statusCode).toBe(400)
  })

  it("treats an empty-string orgId as missing", () => {
    expect(authed({ orgId: "", type: "t", data: {} }).statusCode).toBe(400)
  })
})

describe("org-scoped delivery", () => {
  it("delivers the event to the registered room for that org only", () => {
    const a = fakeOrgRoom()
    const b = fakeOrgRoom()
    register("org-a", a.room)
    register("org-b", b.room)
    const data = { user_id: "u1", presence: "on_break" }

    const res = authed({ orgId: "org-a", type: "member_presence", data })

    expect(res).toEqual({ statusCode: 200, body: { delivered: true } })
    expect(a.handleBridgeEvent).toHaveBeenCalledWith("member_presence", data)
    expect(b.handleBridgeEvent).not.toHaveBeenCalled()
  })

  it("reports delivered=false when no room is live for the org", () => {
    const a = fakeOrgRoom()
    register("org-a", a.room)

    const res = authed({ orgId: "org-b", type: "dev_activity", data: {} })

    expect(res).toEqual({ statusCode: 200, body: { delivered: false, reason: "no active room" } })
    expect(a.handleBridgeEvent).not.toHaveBeenCalled()
  })

  it("stops delivering once the room is unregistered", () => {
    const a = fakeOrgRoom()
    register("org-a", a.room)
    unregisterOrgRoom("org-a", a.room)

    expect(authed({ orgId: "org-a", type: "dev_activity", data: {} }).body)
      .toMatchObject({ delivered: false })
  })

  it("answers 500 without leaking the error when the room handler throws", () => {
    const a = fakeOrgRoom(() => {
      throw new Error("boom with internals")
    })
    register("org-a", a.room)

    expect(authed({ orgId: "org-a", type: "dev_activity", data: {} })).toEqual({
      statusCode: 500,
      body: { error: "internal error" },
    })
  })

  it("never writes a raw newline from the event type into the log line", () => {
    authed({ orgId: "org-zzz", type: "evil\nFORGED LINE", data: {} })
    const lines = logSpy.mock.calls.map((args: unknown[]) => String(args[0]))
    expect(lines.some((line: string) => line.includes("evil\\nFORGED LINE"))).toBe(true)
    expect(lines.every((line: string) => !line.includes("\n"))).toBe(true)
  })
})

describe("room-scoped delivery", () => {
  it("routes a race decline to the registered race room", () => {
    const onInviteeDeclined = vi.fn()
    registerRaceHooks("race-1", { onDispose: vi.fn(), onPhase: vi.fn(), onInviteeDeclined })

    const res = authed({ roomId: "race-1", type: "race_invite_declined", data: { userId: "u2" } })

    expect(res).toEqual({ statusCode: 200, body: { delivered: true } })
    expect(onInviteeDeclined).toHaveBeenCalledWith("u2")
  })

  it("rejects a race decline without a userId", () => {
    const res = authed({ roomId: "race-1", type: "race_invite_declined", data: { userId: 7 } })
    expect(res).toEqual({
      statusCode: 400,
      body: { error: "race_invite_declined needs userId" },
    })
  })

  it("reports whether a backlash decline found its room", () => {
    const decline = vi.fn()
    registerBacklashDeclineHandler("bl-1", decline)

    const hit = authed({ roomId: "bl-1", type: "backlash_invite_declined", data: { userId: "u3" } })
    const miss = authed({ roomId: "bl-2", type: "backlash_invite_declined", data: { userId: "u3" } })

    expect(hit).toEqual({ statusCode: 200, body: { delivered: true } })
    expect(miss).toEqual({ statusCode: 200, body: { delivered: false } })
    expect(decline).toHaveBeenCalledTimes(1)
  })

  it("rejects a backlash decline without a userId", () => {
    const res = authed({ roomId: "bl-1", type: "backlash_invite_declined" })
    expect(res.statusCode).toBe(400)
  })

  it("rejects an unknown room-scoped type with an escaped type name", () => {
    const res = authed({ roomId: "race-1", type: "nope\r\nx", data: {} })
    expect(res).toEqual({
      statusCode: 400,
      body: { error: "unknown room-scoped event type: nope\\r\\nx" },
    })
  })
})
