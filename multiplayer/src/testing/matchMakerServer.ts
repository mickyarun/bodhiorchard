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
 * The real Colyseus matchmaker, in-process, with this server's room
 * definitions. `POST /matchmake/<method>/<room>` is a thin wrapper over the
 * matchmaker calls used here (`joinOrCreate`, `create`, `join`, `joinById`):
 * they run the static onAuth, find or create the room and reserve the seat,
 * exactly as for an HTTP client. `matchmakeOverHttp` goes one step further
 * out, through the controller the HTTP route calls, so it also runs the
 * checks installed there (`installJoinByIdOrgCheck`). Only the WebSocket
 * connect that follows a seat reservation is not replayed.
 */
import {
  LocalDriver,
  LocalPresence,
  matchMaker,
  registerRoomDefinitions,
  unregisterRoomDefinitions,
  type AuthContext,
  type Room,
} from "colyseus"
import { installJoinByIdOrgCheck } from "../auth/joinByIdOrg"
import { roomDefinitions } from "../roomDefinitions"

/** What the HTTP route passes when the request carries no Authorization header. */
export const NO_HEADER_AUTH: AuthContext = { headers: new Headers(), ip: "127.0.0.1" }

/** Boot the matchmaker with every room this server defines. */
export async function startMatchMaker(): Promise<void> {
  await matchMaker.setup(new LocalPresence(), new LocalDriver())
  registerRoomDefinitions(roomDefinitions)
  installJoinByIdOrgCheck()
}

/** A matchmaking request as `POST /matchmake/<method>/<roomName>` runs it. */
export function matchmakeOverHttp(
  method: "joinOrCreate" | "create" | "join" | "joinById",
  roomName: string,
  options: Record<string, unknown>,
): Promise<matchMaker.ISeatReservation> {
  return matchMaker.controller.invokeMethod(method, roomName, options, NO_HEADER_AUTH)
}

/** Every room the matchmaker has listed, as live instances. */
export async function liveRooms(): Promise<Room[]> {
  const listings = await matchMaker.query({})
  return listings.map((listing) => matchMaker.getLocalRoomById(listing.roomId))
}

/** Seats reserved (not yet taken by a WebSocket) in `room`. */
export function reservedSeats(room: Room): number {
  return Object.keys((room as unknown as { _reservedSeats: object })._reservedSeats).length
}

/** Dispose every room (and its seat timers) and forget the room definitions. */
export async function stopMatchMaker(): Promise<void> {
  for (const room of await liveRooms()) {
    const timers = (room as unknown as { _reservedSeatTimeouts: Record<string, NodeJS.Timeout> })
      ._reservedSeatTimeouts
    for (const timer of Object.values(timers)) clearTimeout(timer)
  }
  await Promise.all(matchMaker.disconnectAll())
  unregisterRoomDefinitions(Object.keys(roomDefinitions))
}
