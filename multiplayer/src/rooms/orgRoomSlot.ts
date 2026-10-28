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
 * An org has one garden room: backend events reach the org through the one
 * room that holds its bridge slot, so a second room would see none of them.
 *
 * A second room is asked for in two ways, both by verified members of the
 * org (the static join check refuses everyone else before matchmaking):
 * a direct `create("org", ...)`, or a `joinOrCreate` that finds the open room
 * full (`maxClients`) and so creates one. Both are refused with a clean
 * matchmaking error that says which it was, rather than splitting the org
 * across rooms; a member who finds the garden full can retry once someone
 * leaves.
 */
import { ErrorCode, ServerError } from "colyseus"
import { registerOrgRoom } from "../bridge/BridgeEndpoint"
import type { OrgRoom } from "./OrgRoom"

export const ORG_ROOM_FULL = "this org's garden is full, try again shortly"
export const ORG_ROOM_TAKEN = "this org already has an open room"

/** Claim the org's bridge slot for `room`, or refuse the room's creation. */
export function claimOrgRoomSlot(orgId: string, room: OrgRoom): void {
  const holder = registerOrgRoom(orgId, room)
  if (holder === room) return
  const reason = holder.hasReachedMaxClients() ? ORG_ROOM_FULL : ORG_ROOM_TAKEN
  throw new ServerError(ErrorCode.MATCHMAKE_INVALID_CRITERIA, reason)
}
