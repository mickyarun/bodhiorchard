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
 * How many mini-game rooms one player may hold open at once.
 *
 * Every `create("minigame")` opens a fresh room, and a room lives until its
 * seat reservation lapses even if the player never connects, so without a
 * cap one valid token could open rooms without limit. A play uses one room
 * and the frontend leaves it before starting the next, so a small cap leaves
 * room for a second tab without bounding normal play.
 *
 * The cap is keyed on the verified user id, which is only known in the
 * static `onAuth` (before the room exists) and in `onJoin`. So a slot is
 * taken in the static `onAuth`, held as pending until the player connects,
 * bound to the room in `onJoin` and released in `onDispose`. A pending slot
 * lapses shortly after the seat reservation it was taken for, which is when
 * a never-joined room disposes itself.
 */
import type { AuthContext } from "colyseus"
import { authenticateJoin } from "../auth/roomAuth"
import { refuseJoin, type JoinCredentials, type JoinIdentity } from "../auth/verifyJoin"

/** Mini-game rooms one player may hold open at the same time. */
export const MAX_OPEN_MINIGAMES_PER_USER = 3
/** Seconds a mini-game seat stays reserved for a player who has not connected. */
export const MINIGAME_SEAT_SECONDS = 15
/** How long a pending slot outlives its seat, so the room is gone before the slot is. */
const PENDING_SLOT_GRACE_MS = 1000
export const PENDING_SLOT_MS = MINIGAME_SEAT_SECONDS * 1000 + PENDING_SLOT_GRACE_MS

interface PlayerSlots {
  pending: NodeJS.Timeout[]
  rooms: Set<string>
}

const slotsByUser = new Map<string, PlayerSlots>()
const ownerByRoom = new Map<string, string>()

/** Mini-game rooms `userId` holds open or has a pending seat for. */
export function openMinigameSlots(userId: string): number {
  const held = slotsByUser.get(userId)
  return held ? held.pending.length + held.rooms.size : 0
}

/** Take a pending slot for `userId`; false when they already hold the most allowed. */
export function takeMinigameSlot(userId: string): boolean {
  if (openMinigameSlots(userId) >= MAX_OPEN_MINIGAMES_PER_USER) return false
  const held = slotsOf(userId)
  const lapse = setTimeout(() => {
    held.pending = held.pending.filter((timer) => timer !== lapse)
    forgetIfEmpty(userId)
  }, PENDING_SLOT_MS)
  lapse.unref()
  held.pending.push(lapse)
  return true
}

/** The player joined `roomId`: turn one of their pending slots into that room's. */
export function bindMinigameSlot(userId: string, roomId: string): void {
  const held = slotsOf(userId)
  const pending = held.pending.shift()
  if (pending) clearTimeout(pending)
  held.rooms.add(roomId)
  ownerByRoom.set(roomId, userId)
}

/** `roomId` was disposed: free the slot its player held for it. */
export function releaseMinigameSlot(roomId: string): void {
  const userId = ownerByRoom.get(roomId)
  if (userId === undefined) return
  ownerByRoom.delete(roomId)
  slotsByUser.get(userId)?.rooms.delete(roomId)
  forgetIfEmpty(userId)
}

/**
 * Static `onAuth` for the mini-game room: the shared join check, then a slot
 * for the verified player, before matchmaking creates the room.
 */
export async function authenticateMinigameJoin(
  headerToken: string | undefined,
  options: (JoinCredentials & Record<string, unknown>) | undefined,
  context?: AuthContext,
): Promise<JoinIdentity> {
  const identity = await authenticateJoin(headerToken, options, context)
  if (!takeMinigameSlot(identity.userId)) {
    throw refuseJoin("too many open mini-games", identity.orgId)
  }
  return identity
}

function slotsOf(userId: string): PlayerSlots {
  let held = slotsByUser.get(userId)
  if (!held) {
    held = { pending: [], rooms: new Set() }
    slotsByUser.set(userId, held)
  }
  return held
}

function forgetIfEmpty(userId: string): void {
  const held = slotsByUser.get(userId)
  if (held && held.pending.length === 0 && held.rooms.size === 0) slotsByUser.delete(userId)
}
