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
 * The room-org check for `joinById`, run before Colyseus reserves the seat.
 *
 * `joinOrCreate`, `join` and `create` land in a room of the org the client
 * names, because every room definition files its rooms under `orgId`
 * (`roomDefinitions.ts`), and the static `onAuth` verifies the token for that
 * org. `joinById` names a room instead, and Colyseus hands the static
 * `onAuth` no room id. Without this check a verified member of org B naming
 * org B could reserve seats in any room whose id they know, holding each one
 * until its reservation lapsed, and so lock a room's own org out of it.
 *
 * Every matchmaking request a client sends (`POST /matchmake/<method>/<room>`)
 * goes through `matchMaker.controller.invokeMethod`, which for `joinById`
 * receives the room id. `installJoinByIdOrgCheck` wraps it so a `joinById`
 * goes ahead only when the org the client names is the org the room's
 * listing is filed under; the static `onAuth` then verifies the token for
 * that same org. A room listed without an org cannot be joined by id.
 */
import { matchMaker } from "colyseus"
import { refuseJoin } from "./verifyJoin"

/** A room as the matchmaker lists it. */
type RoomListing = Awaited<ReturnType<typeof matchMaker.query>>[number]

/** The org a room was filed under at creation (its `orgId` filter), or "". */
export function listedRoomOrg(listing: RoomListing): string {
  const orgId: unknown = listing.metadata?.orgId
  return typeof orgId === "string" ? orgId : ""
}

/**
 * Refuse a `joinById` into `roomId` unless `options` name the org that room
 * belongs to. A room that does not exist is left to the matchmaker to report.
 */
export async function requireJoinByIdOrg(roomId: string, options: unknown): Promise<void> {
  const [listing] = await matchMaker.query({ roomId })
  if (!listing) return
  const roomOrg = listedRoomOrg(listing)
  const claimedOrg = (options as { orgId?: unknown } | undefined)?.orgId
  if (!roomOrg || claimedOrg !== roomOrg) {
    throw refuseJoin("join org is not this room's org", roomOrg)
  }
}

let installed = false

/** Run `requireJoinByIdOrg` ahead of every client `joinById`. Safe to call twice. */
export function installJoinByIdOrgCheck(): void {
  if (installed) return
  installed = true
  const { controller } = matchMaker
  const invokeMethod = controller.invokeMethod.bind(controller)
  controller.invokeMethod = async (method, roomName, clientOptions, authOptions) => {
    if (method === "joinById") await requireJoinByIdOrg(roomName, clientOptions)
    return invokeMethod(method, roomName, clientOptions, authOptions)
  }
}
