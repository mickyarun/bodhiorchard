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
 * Test harness for RaceRoom. Rooms are created the way OrgRaceHandler does
 * (with a create ticket), clients join the way Colyseus runs a join (onAuth,
 * then onJoin with its result), and messages go through the room's
 * registered handlers. The fake backend verifies the token `jwt-<userId>` as
 * that user in `RACE_ORG`, named `<userId> (verified)`.
 */
import type { Client } from "colyseus"
import { vi, type Mock } from "vitest"
import { issueRaceCreateTicket } from "../bridge/RaceCreateTickets"
import { RaceRoom } from "../rooms/RaceRoom"

export const RACE_ORG = "org-a"

/** The display name the fake backend gives `userId`. */
export function verifiedName(userId: string): string {
  return `${userId} (verified)`
}

/** Answer verify-token for `jwt-<userId>`; every other backend call gets `{}`. */
export function fakeBackend(fetchMock: Mock): void {
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    if (!String(url).endsWith("/verify-token")) return new Response("{}")
    const { token } = JSON.parse(String(init?.body)) as { token: string }
    const userId = token.replace(/^jwt-/, "")
    return Response.json({
      valid: true,
      user_id: userId,
      org_id: RACE_ORG,
      name: verifiedName(userId),
    })
  })
}

/** A lobby created by the server for `host`, inviting `invitedUserIds`. */
export function createRaceRoom(options: Record<string, unknown> = {}): RaceRoom {
  const room = new RaceRoom()
  room.roomId = "race-test"
  room.onCreate({
    createTicket: issueRaceCreateTicket(),
    orgId: RACE_ORG,
    hostUserId: "host",
    hostName: "Host",
    distanceM: 100,
    invitedUserIds: ["guest"],
    ...options,
  })
  return room
}

/** Dispatch a client message through the room's registered handler. */
export function send(room: RaceRoom, client: Client, type: string, payload?: unknown): void {
  const events = (room as unknown as {
    onMessageEvents: { emit(type: string, client: Client, message: unknown): void }
  }).onMessageEvents
  events.emit(type, client, payload)
}

/** Join the room with these raw options: onAuth, then onJoin with its result. */
export async function connect(
  room: RaceRoom,
  sessionId: string,
  options: Record<string, string>,
): Promise<Client> {
  const client = { sessionId, userData: undefined, send: vi.fn() } as unknown as Client
  const auth = await room.onAuth(client, options)
  room.onJoin(client, options, auth)
  room.clients.push(client)
  return client
}

/** Join as `userId` with their own token, then ask for a racer slot. */
export async function join(room: RaceRoom, sessionId: string, userId: string): Promise<Client> {
  const client = await connect(room, sessionId, { token: `jwt-${userId}` })
  send(room, client, "race_join", { userId, name: userId })
  return client
}
