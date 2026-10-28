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
 * Where every room runs the join check, and the room-level org check after it.
 *
 * Colyseus runs a room's instance-level `onAuth` only once the client opens
 * its WebSocket, which is AFTER matchmaking has created the room (if none was
 * open) and reserved the client a seat. An unauthenticated client could
 * therefore create rooms and hold seats it would never be allowed to use, up
 * to `maxClients`, locking real members out. The static `onAuth` hook runs
 * inside the matchmaker instead, before it looks for a room, creates one or
 * reserves a seat, for every `joinOrCreate`, `create`, `join` and `joinById`.
 *
 * So every room class sets `static onAuth = authenticateJoin` (the room
 * registry test holds every registered room to it). It verifies the join
 * token against the org the client names in its options (`orgId`, which must
 * be a canonical lowercase UUID) with the shared `verifyJoin`, and refuses
 * anything else. Colyseus hands the identity it returns to the room as
 * `client.auth` and as `onJoin`'s third argument, and skips any instance
 * `onAuth`, so a join costs one backend call.
 *
 * The static hook does not know which room the client will land in. For
 * `joinOrCreate`, `join` and `create` that is the org it named (the shared
 * rooms filter on `orgId`). For `joinById`, Colyseus gives the hook no room
 * id, so a verified member of org B who names org B and knows the id of an
 * org A room (ids are only published inside org A's garden state) is still
 * granted a seat reservation there. Each room's `onJoin` therefore calls
 * `requireRoomIdentity` with its own org and refuses that join before it acts
 * on the identity; the reserved seat is released when the reservation lapses.
 *
 * The token travels in the join options (`options.token`), which is what the
 * frontend sends; the `Authorization` header token Colyseus also offers is
 * not used, so there is one transport to reason about.
 */
import type { AuthContext } from "colyseus"
import { isUuid } from "../bridge/uuid"
import {
  refuseJoin,
  requireJoinIdentity,
  verifyJoin,
  type JoinCredentials,
  type JoinIdentity,
} from "./verifyJoin"

/**
 * Static `onAuth` for every room: verify the join before matchmaking reserves
 * a seat or creates a room. Throws (a refused join) on any doubt.
 */
export async function authenticateJoin(
  _headerToken: string | undefined,
  options: (JoinCredentials & Record<string, unknown>) | undefined,
  _context?: AuthContext,
): Promise<JoinIdentity> {
  const claimedOrg = options?.orgId
  if (!isUuid(claimedOrg)) throw refuseJoin("join must name its org", String(claimedOrg ?? ""))
  return verifyJoin(options, claimedOrg)
}

/**
 * For `onJoin`: the identity `authenticateJoin` accepted, provided it belongs
 * to this room's org. Refuses a join that skipped the check or names another org.
 */
export function requireRoomIdentity(auth: JoinIdentity | undefined, roomOrgId: string): JoinIdentity {
  const identity = requireJoinIdentity(auth)
  if (!roomOrgId || identity.orgId !== roomOrgId) {
    throw refuseJoin("join org is not this room's org", roomOrgId)
  }
  return identity
}
