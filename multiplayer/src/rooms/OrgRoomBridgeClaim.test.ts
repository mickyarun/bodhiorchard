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
 * OrgRoom.onCreate runs before onAuth, so any client can `create("org",
 * {orgId})` for an org it does not belong to. That room used to overwrite the
 * bridge registry entry for the org, and its dispose then removed the entry
 * of the room the org's members were actually in, so backend events stopped
 * reaching them. These tests drive the real bridge endpoint to see which room
 * an org's events land in.
 */
import type { Request, Response } from "express"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { handleBridgePublish } from "../bridge/BridgeEndpoint"
import { OrgRoomState } from "../schema/OrgRoomState"
import { OrgRoom } from "./OrgRoom"

const ORG_ID = "0b4f4f53-58a4-4c55-9a0e-6f1c2b7d9e10"
const BRIDGE_SECRET = process.env.COLYSEUS_BRIDGE_SECRET ?? "dev-colyseus-bridge-secret"
const fetchMock = vi.fn()
const openRooms: OrgRoom[] = []

/** Publish a bridge event for `orgId`; returns whether a room received it. */
function publish(orgId: string): boolean {
  let body: { delivered?: boolean } = {}
  const req = {
    header: () => BRIDGE_SECRET,
    body: { orgId, type: "unhandled_probe", data: {} },
  } as unknown as Request
  const res = {
    status: () => res,
    json: (payload: { delivered?: boolean }) => {
      body = payload
      return res
    },
  } as unknown as Response
  handleBridgePublish(req, res)
  return body.delivered === true
}

async function openRoom(orgId: string): Promise<OrgRoom> {
  const room = new OrgRoom()
  openRooms.push(room)
  await room.onCreate({ orgId })
  return room
}

function closeRoom(room: OrgRoom): void {
  room.setSimulationInterval(undefined)
  room.clock.clear()
  if (room.state) room.onDispose()
}

beforeEach(() => {
  fetchMock.mockReset()
  fetchMock.mockResolvedValue(Response.json({ orgId: ORG_ID, members: [], repos: [] }))
  vi.stubGlobal("fetch", fetchMock)
  vi.spyOn(console, "log").mockImplementation(() => undefined)
  vi.spyOn(console, "warn").mockImplementation(() => undefined)
})

afterEach(() => {
  for (const room of openRooms.splice(0)) closeRoom(room)
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe("a second org room for the same org", () => {
  it("is refused and the open room keeps the org's bridge events", async () => {
    const real = await openRoom(ORG_ID)
    const received = vi.spyOn(real, "handleBridgeEvent")

    await expect(openRoom(ORG_ID)).rejects.toThrow("already has an open room")

    expect(publish(ORG_ID)).toBe(true)
    expect(received).toHaveBeenCalledTimes(1)
  })

  it("starts no simulation timer when refused", async () => {
    await openRoom(ORG_ID)
    const impostor = new OrgRoom()

    await expect(impostor.onCreate({ orgId: ORG_ID })).rejects.toThrow()

    expect((impostor as unknown as { _simulationInterval?: unknown })._simulationInterval)
      .toBeUndefined()
  })

  it("cannot evict the open room when it is disposed", async () => {
    const real = await openRoom(ORG_ID)
    const received = vi.spyOn(real, "handleBridgeEvent")
    const impostor = new OrgRoom()
    await expect(impostor.onCreate({ orgId: ORG_ID })).rejects.toThrow()

    // Even a room that reached dispose with the victim's org id in its state
    // must not release a slot it never held.
    impostor.setState(new OrgRoomState())
    impostor.state.orgId = ORG_ID
    impostor.onDispose()

    expect(publish(ORG_ID)).toBe(true)
    expect(received).toHaveBeenCalledTimes(1)
  })

  it("can be opened once the previous room has been disposed", async () => {
    const first = await openRoom(ORG_ID)
    closeRoom(first)
    openRooms.splice(openRooms.indexOf(first), 1)

    const second = await openRoom(ORG_ID)
    const received = vi.spyOn(second, "handleBridgeEvent")

    expect(publish(ORG_ID)).toBe(true)
    expect(received).toHaveBeenCalledTimes(1)
  })
})

describe("org id validation", () => {
  it.each([
    ["a non-UUID string", "org-a"],
    ["a path segment", "../../admin"],
    ["a UUID with a suffix", `${ORG_ID}/x`],
    ["an empty string", ""],
    ["a missing id", undefined],
  ])("refuses %s before registering or fetching", async (_label, orgId) => {
    const room = new OrgRoom()

    await expect(room.onCreate({ orgId })).rejects.toThrow("orgId must be a UUID")

    expect(fetchMock).not.toHaveBeenCalled()
    if (orgId) expect(publish(orgId)).toBe(false)
  })
})
