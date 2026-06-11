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
 * OrgRaceHandler — wires the `race_create` message on OrgRoom into the
 * race-v2 server flow without growing OrgRoom.ts past its size budget.
 *
 * Responsibilities:
 *   - Validate the incoming `race_create` payload (array of invitees,
 *     distance in the allowed set, message sender is the claimed host).
 *   - Spin up a new RaceRoom via `matchMaker.createRoom`.
 *   - Populate `OrgRoomState.activeRaces` with an `ActiveRaceSummary`.
 *   - Register a dispose callback in the RaceRegistry so the summary
 *     disappears when the race ends.
 *   - Reply to the creator via `client.send("race_created", { roomId })`
 *     and `client.send("race_create_failed", { reason })` on failure.
 *   - Call `postRaceInvite` for each invitee — failures here are logged
 *     but don't roll back the race-room creation (a missed toast is
 *     recoverable; the invite still sits in the bell dropdown).
 */
import type { Client, Room } from "colyseus"
import type { OrgRoomState } from "../schema/OrgRoomState"
import { ArraySchema } from "@colyseus/schema"
import { ActiveRaceSummary } from "../schema/ActiveRaceSummary"
import {
  ALLOWED_DISTANCES_M,
  ALLOWED_TRACK_SHAPES,
  MAX_RACERS,
} from "../../../shared/race/RaceConstants"
import type { TrackShape } from "../../../shared/race/types"
import { postRaceInvite } from "../bridge/BackendClient"
import { registerRaceHooks } from "../bridge/RaceRegistry"
import { isProductionServer, resolveBotCount } from "./RaceRoomHelpers"
import { RaceRoom } from "./RaceRoom"

export interface RaceCreateMessage {
  invitedUserIds: string[]
  distanceM: number
  trackShape: TrackShape
  /**
   * Dev-mode test bots requested by the host. Parsed here only for type
   * safety; the authoritative clamp AND the production force-to-0 gate
   * live in RaceRoomHelpers.resolveBotCount on the room-create path.
   */
  botCount: number
}

/**
 * Install the `race_create` handler on the given OrgRoom instance.
 * Returns nothing — the handler is registered with the room's own
 * `onMessage` plumbing.
 */
export function installRaceCreateHandler(room: Room<{ state: OrgRoomState }>): void {
  room.onMessage("race_create", (client, rawData) => {
    void handleRaceCreate(room, client, rawData)
  })
}

async function handleRaceCreate(
  room: Room<{ state: OrgRoomState }>,
  client: Client,
  raw: unknown,
): Promise<void> {
  const parsed = parseRaceCreateMessage(raw)
  if (!parsed) {
    client.send("race_create_failed", { reason: "invalid_payload" })
    return
  }

  const userData = client.userData as { userId?: string; name?: string } | undefined
  const hostUserId = userData?.userId
  const hostName = userData?.name ?? "Player"
  if (!hostUserId) {
    client.send("race_create_failed", { reason: "unauthenticated" })
    return
  }

  // Total racers = host + invitees + dev-mode bots. Resolve the bot count
  // through the same prod-gate + clamp the room applies, so the cap is
  // honest (a 7-bot dev race with invitees can't silently overflow the
  // room's MAX_RACERS join cap and drop seats). In production the gate
  // forces bots to 0, so this reduces to host + invitees.
  const botCount = resolveBotCount(parsed.botCount, isProductionServer())
  const racerCount = raceRacerCount(parsed.invitedUserIds.length, botCount)
  if (racerCount > MAX_RACERS) {
    client.send("race_create_failed", { reason: "too_many_invitees" })
    return
  }

  const orgId = room.state.orgId
  try {
    const matchMakerMod = await import("colyseus")
    const newRoom = await matchMakerMod.matchMaker.createRoom("race", {
      orgId,
      hostUserId,
      hostName,
      distanceM: parsed.distanceM,
      trackShape: parsed.trackShape,
      invitedUserIds: parsed.invitedUserIds,
      botCount: parsed.botCount,
    })

    addActiveRace(
      room, newRoom.roomId, hostUserId, hostName, parsed.distanceM, racerCount,
      [hostUserId, ...parsed.invitedUserIds],
    )
    registerRaceHooks(newRoom.roomId, {
      onDispose: () => {
        // Schema MapSchema uses delete/set like a native Map. Safe to call
        // even if the entry was already removed by the phase handler below.
        room.state.activeRaces.delete(newRoom.roomId)
      },
      onPhase: (phase: string) => {
        const summary = room.state.activeRaces.get(newRoom.roomId)
        if (!summary) return
        // Once a race finishes the room still exists (clients read final
        // placings) but the watch banner shouldn't keep pointing at it.
        // Drop the summary immediately — the final `onDispose` callback
        // will be a no-op for this entry.
        if (phase === "finished") {
          room.state.activeRaces.delete(newRoom.roomId)
          return
        }
        summary.phase = phase
      },
      onInviteeDeclined: (userId: string) => {
        // `matchMaker.createRoom` resolves to an `IRoomCache` lookup stub,
        // not the live Room instance — so `newRoom instanceof RaceRoom`
        // is always false. Resolve the instance via `getLocalRoomById`,
        // which is the single-process Colyseus API for "give me the actual
        // Room object that's running right here."
        const instance = matchMakerMod.matchMaker.getLocalRoomById(newRoom.roomId)
        if (instance instanceof RaceRoom) instance.removeInvitee(userId)
      },
    })

    client.send("race_created", { roomId: newRoom.roomId })

    // Fire invites in parallel. Any individual failure is logged by the
    // BackendClient helper and does not affect the others.
    await Promise.all(
      parsed.invitedUserIds.map((recipientUserId) =>
        postRaceInvite({
          orgId,
          recipientUserId,
          hostUserId,
          hostName,
          roomId: newRoom.roomId,
          distanceM: parsed.distanceM,
        }),
      ),
    )
  } catch (err) {
    console.error(`[OrgRoom ${orgId}] race_create failed:`, err)
    client.send("race_create_failed", { reason: "server_error" })
  }
}

function addActiveRace(
  room: Room<{ state: OrgRoomState }>,
  roomId: string,
  hostUserId: string,
  hostName: string,
  distanceM: number,
  racerCount: number,
  participantUserIds: readonly string[],
): void {
  const summary = new ActiveRaceSummary()
  summary.roomId = roomId
  summary.hostUserId = hostUserId
  summary.hostName = hostName
  summary.distanceM = distanceM
  summary.phase = "lobby"
  summary.racerCount = racerCount
  summary.participantUserIds = new ArraySchema<string>(...participantUserIds)
  room.state.activeRaces.set(roomId, summary)
}

/**
 * Total racers a create request would seat: host (the +1) + human
 * invitees + already-resolved dev bots. Compared against MAX_RACERS to
 * reject over-capacity races. Pure so the occupancy cap is unit-testable
 * without standing up a matchMaker / Room.
 */
export function raceRacerCount(inviteeCount: number, botCount: number): number {
  return inviteeCount + 1 + botCount
}

export function parseRaceCreateMessage(raw: unknown): RaceCreateMessage | null {
  if (typeof raw !== "object" || raw === null) return null
  const o = raw as Record<string, unknown>
  if (!Array.isArray(o.invitedUserIds)) return null
  const invited: string[] = []
  for (const v of o.invitedUserIds) {
    if (typeof v !== "string" || v.length === 0) return null
    invited.push(v)
  }
  if (typeof o.distanceM !== "number") return null
  if (!(ALLOWED_DISTANCES_M as readonly number[]).includes(o.distanceM)) return null
  // Optional for pre-circuit clients: absent → 'straight'. A present but
  // unrecognised value is rejected outright, like a bad distance.
  let trackShape: TrackShape = "straight"
  if (o.trackShape !== undefined) {
    if (
      typeof o.trackShape !== "string" ||
      !(ALLOWED_TRACK_SHAPES as readonly string[]).includes(o.trackShape)
    ) {
      return null
    }
    trackShape = o.trackShape as TrackShape
  }
  // Optional dev-bot count: absent → 0; a present non-integer is rejected
  // outright, like a bad trackShape. Range clamping (and the production
  // force-to-0) is centralised in RaceRoomHelpers.resolveBotCount.
  let botCount = 0
  if (o.botCount !== undefined) {
    if (typeof o.botCount !== "number" || !Number.isInteger(o.botCount)) return null
    botCount = o.botCount
  }
  return { invitedUserIds: invited, distanceM: o.distanceM, trackShape, botCount }
}
