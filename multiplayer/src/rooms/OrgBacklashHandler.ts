// Copyright 2025-2026 Arun Rajkumar
// Licensed under the Apache License, Version 2.0

import { ArraySchema } from "@colyseus/schema"
import { matchMaker, type Client, type Room } from "colyseus"
import { BACKLASH_MAX_VIEWERS } from "../../../shared/minigames/backlashSocial"
import type { OrgRoomState } from "../schema/OrgRoomState"
import { postBacklashInvite } from "../bridge/BackendClient"
import { registerBacklashSummaryHooks } from "../bridge/BacklashRegistry"
import { ActiveBacklashSummary } from "../schema/ActiveBacklashSummary"

interface BacklashCreateMessage {
  invitedUserId: string
}

const USER_ID_MAX_LENGTH = 64

export function installBacklashCreateHandler(room: Room<{ state: OrgRoomState }>): void {
  room.onMessage("backlash_create", (client, raw) => {
    void handleBacklashCreate(room, client, raw)
  })
}

export function parseBacklashCreateMessage(raw: unknown): BacklashCreateMessage | null {
  if (typeof raw !== "object" || raw === null) return null
  const invitedUserId = (raw as { invitedUserId?: unknown }).invitedUserId
  if (
    typeof invitedUserId !== "string"
    || invitedUserId.length === 0
    || invitedUserId.length > USER_ID_MAX_LENGTH
  ) return null
  return { invitedUserId }
}

async function handleBacklashCreate(
  room: Room<{ state: OrgRoomState }>,
  client: Client,
  raw: unknown,
): Promise<void> {
  const parsed = parseBacklashCreateMessage(raw)
  if (!parsed) {
    client.send("backlash_create_failed", { reason: "invalid_payload" })
    return
  }
  const userData = client.userData as { userId?: string; name?: string } | undefined
  const hostUserId = userData?.userId ?? ""
  if (!hostUserId) {
    client.send("backlash_create_failed", { reason: "unauthenticated" })
    return
  }
  if (parsed.invitedUserId === hostUserId) {
    client.send("backlash_create_failed", { reason: "cannot_invite_self" })
    return
  }

  try {
    const created = await matchMaker.createRoom("backlash", {
      orgId: room.state.orgId,
      hostUserId,
      invitedUserId: parsed.invitedUserId,
    })
    const invited = await postBacklashInvite({
      orgId: room.state.orgId,
      recipientUserId: parsed.invitedUserId,
      hostUserId,
      hostName: userData?.name?.trim() || "Player",
      roomId: created.roomId,
    })
    if (!invited) {
      const liveRoom = matchMaker.getLocalRoomById(created.roomId)
      await liveRoom?.disconnect()
      client.send("backlash_create_failed", { reason: "invite_delivery_failed" })
      return
    }
    addActiveBacklash(
      room,
      created.roomId,
      hostUserId,
      userData?.name?.trim() || "Player",
      parsed.invitedUserId,
    )
    registerBacklashSummaryHooks(created.roomId, {
      onDispose: () => room.state.activeBacklashes.delete(created.roomId),
      onPhase: (phase) => {
        const summary = room.state.activeBacklashes.get(created.roomId)
        if (!summary) return
        summary.phase = phase
      },
      onViewerCount: (viewerCount) => {
        const summary = room.state.activeBacklashes.get(created.roomId)
        if (summary) {
          summary.viewerCount = Math.max(0, Math.min(BACKLASH_MAX_VIEWERS, viewerCount))
        }
      },
    })
    client.send("backlash_created", { roomId: created.roomId })
  } catch (error) {
    console.error("[OrgBacklashHandler] room creation failed", error)
    client.send("backlash_create_failed", { reason: "server_error" })
  }
}

export function addActiveBacklash(
  room: Room<{ state: OrgRoomState }>,
  roomId: string,
  hostUserId: string,
  hostName: string,
  invitedUserId: string,
): void {
  const summary = new ActiveBacklashSummary()
  summary.roomId = roomId
  summary.hostUserId = hostUserId
  summary.hostName = hostName
  summary.invitedName = room.state.members.get(invitedUserId)?.name?.trim() || "Opponent"
  summary.phase = "lobby"
  summary.participantUserIds = new ArraySchema<string>(hostUserId, invitedUserId)
  room.state.activeBacklashes.set(roomId, summary)
}
