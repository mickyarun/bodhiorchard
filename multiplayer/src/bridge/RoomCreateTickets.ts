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
 * One-time tickets that let the server, and only the server, create a room.
 *
 * Colyseus lets any client call `create(name, options)`. Race and backlash
 * rooms take their org, host and invitees from those create options, and are
 * meant to be opened only by the OrgRoom handlers (`OrgRaceHandler`,
 * `OrgBacklashHandler`) for the verified host, which also deliver the
 * invites. So the handler opens the room through `createServerRoom`, which
 * issues a ticket bound to that room type and passes it in the create
 * options, and the room's onCreate consumes it with `requireRoomCreateTicket`.
 * A ticket never leaves the process, works once, for one room type, and is
 * revoked if the create fails before the room consumed it.
 */
import { randomUUID } from "node:crypto"
import { matchMaker } from "colyseus"

/** Room types that only the server may create. */
export type ServerCreatedRoom = "race" | "backlash"

/** The create option that carries the ticket. */
export const CREATE_TICKET_OPTION = "createTicket"

const outstanding = new Map<string, ServerCreatedRoom>()

/** A fresh ticket for one `matchMaker.createRoom(room, ...)` call. */
export function issueRoomCreateTicket(room: ServerCreatedRoom): string {
  const ticket = randomUUID()
  outstanding.set(ticket, room)
  return ticket
}

/** True, once, for a ticket this process issued for `room`; false for anything else. */
export function consumeRoomCreateTicket(room: ServerCreatedRoom, ticket: unknown): boolean {
  if (typeof ticket !== "string" || outstanding.get(ticket) !== room) return false
  return outstanding.delete(ticket)
}

/** Drop a ticket that was not consumed (the create failed early). */
export function revokeRoomCreateTicket(ticket: string): void {
  outstanding.delete(ticket)
}

/** For a room's onCreate: consume the ticket in its create options, or refuse the create. */
export function requireRoomCreateTicket(room: ServerCreatedRoom, createOptions: unknown): void {
  const ticket =
    typeof createOptions === "object" && createOptions !== null
      ? (createOptions as Record<string, unknown>)[CREATE_TICKET_OPTION]
      : undefined
  if (!consumeRoomCreateTicket(room, ticket)) {
    throw new Error(`${room} rooms are created by the server`)
  }
}

/** Open a `room` the way only the server can: with a ticket in its create options. */
export async function createServerRoom(
  room: ServerCreatedRoom,
  options: Record<string, unknown>,
): ReturnType<typeof matchMaker.createRoom> {
  const ticket = issueRoomCreateTicket(room)
  try {
    return await matchMaker.createRoom(room, { ...options, [CREATE_TICKET_OPTION]: ticket })
  } finally {
    revokeRoomCreateTicket(ticket)
  }
}
