// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
import { ALLOWED_DISTANCES_M, MAX_RACERS } from "../../../shared/race/RaceConstants"
import { postRaceInvite } from "../bridge/BackendClient"
import { registerRaceHooks } from "../bridge/RaceRegistry"

export interface RaceCreateMessage {
  invitedUserIds: string[]
  distanceM: number
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

  // Host must include themselves in the racer count; total racers is
  // invitees + host. Cap at MAX_RACERS so a host can't spin up an 11-person
  // race that RaceRoom would reject anyway.
  const racerCount = parsed.invitedUserIds.length + 1
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
      invitedUserIds: parsed.invitedUserIds,
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
  return { invitedUserIds: invited, distanceM: o.distanceM }
}
