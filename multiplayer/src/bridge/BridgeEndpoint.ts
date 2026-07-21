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
 * BridgeEndpoint — HTTP endpoint that receives events from the backend.
 *
 * The Python backend publishes dev_activity, agent_activity, and member
 * presence change events to this endpoint. Events are routed to the
 * appropriate OrgRoom instance via Colyseus matchMaker.
 *
 * Authentication: shared secret in the `X-Bridge-Secret` header.
 * Request body: { orgId, type, data }
 *
 * Note: The room registry is populated by OrgRoom lifecycle hooks
 * (onCreate / onDispose) so we can dispatch events without needing
 * the Colyseus matchMaker query API on every call.
 */
import type { Request, Response } from "express"
import { timingSafeEqual } from "crypto"
import { OrgRoom } from "../rooms/OrgRoom"
import { fireRaceInviteDeclined } from "./RaceRegistry"
import { fireBacklashInviteDeclined } from "./BacklashRegistry"
import { safeLog } from "./logSanitize"

// Fail-closed in production: if the secret isn't configured, refuse to start.
// In dev/test we allow a well-known placeholder so local tooling works without
// env setup, but the warning is loud.
const DEV_DEFAULT_SECRET = "dev-colyseus-bridge-secret"
const isProduction = process.env.NODE_ENV === "production"

if (!process.env.COLYSEUS_BRIDGE_SECRET) {
  if (isProduction) {
    throw new Error(
      "[BridgeEndpoint] COLYSEUS_BRIDGE_SECRET must be set in production. " +
      "Refusing to start with the dev default secret.",
    )
  }
  console.warn(
    "[BridgeEndpoint] WARNING: COLYSEUS_BRIDGE_SECRET not set — using dev default. " +
    "DO NOT deploy to production without setting this env var."
  )
}

const BRIDGE_SECRET = process.env.COLYSEUS_BRIDGE_SECRET ?? DEV_DEFAULT_SECRET
const BRIDGE_SECRET_BUF = Buffer.from(BRIDGE_SECRET)

/** Constant-time comparison of the incoming secret against the configured one. */
function verifyBridgeSecret(provided: string | undefined): boolean {
  if (!provided) return false
  const providedBuf = Buffer.from(provided)
  if (providedBuf.length !== BRIDGE_SECRET_BUF.length) return false
  return timingSafeEqual(providedBuf, BRIDGE_SECRET_BUF)
}

// In-memory registry of active OrgRoom instances by orgId.
// Populated by OrgRoom on create, cleared on dispose.
const orgRooms = new Map<string, OrgRoom>()

export function registerOrgRoom(orgId: string, room: OrgRoom): void {
  orgRooms.set(orgId, room)
  console.log(`[BridgeEndpoint] Registered org=${orgId} (total=${orgRooms.size})`)
}

export function unregisterOrgRoom(orgId: string): void {
  orgRooms.delete(orgId)
  console.log(`[BridgeEndpoint] Unregistered org=${orgId} (total=${orgRooms.size})`)
}

/**
 * Two envelope shapes are accepted — exactly one of `orgId` / `roomId`
 * must be present so the routing is unambiguous:
 *
 *   - `{orgId, type, data}` — org-scoped: routed to the active OrgRoom
 *     for that org. Used by dev_activity, agent_activity, member_presence.
 *   - `{roomId, type, data}` — room-scoped: routed through the
 *     RaceRegistry to a specific RaceRoom. Used by race_invite_declined.
 *
 * Previously the single `{orgId, type, data}` shape served both, with
 * a `type === "race_invite_declined"` branch silently ignoring `orgId`.
 * That implicit contract drifted on cross-org edges (host's tab gone,
 * orgId stale). The split makes the routing key explicit.
 */
interface BridgePayload {
  orgId?: string
  roomId?: string
  type: string
  data: Record<string, unknown>
}

export function handleBridgePublish(req: Request, res: Response): void {
  // Verify shared secret (constant-time comparison)
  if (!verifyBridgeSecret(req.header("x-bridge-secret"))) {
    res.status(401).json({ error: "invalid bridge secret" })
    return
  }

  const payload = req.body as BridgePayload
  if (!payload?.type) {
    res.status(400).json({ error: "missing type" })
    return
  }
  const hasOrg = typeof payload.orgId === "string" && payload.orgId.length > 0
  const hasRoom = typeof payload.roomId === "string" && payload.roomId.length > 0
  if (hasOrg === hasRoom) {
    res.status(400).json({ error: "exactly one of orgId or roomId is required" })
    return
  }

  if (hasRoom) {
    if (!dispatchRoomScoped(payload, res)) return
    return
  }

  const room = orgRooms.get(payload.orgId!)
  if (!room) {
    // No active OrgRoom for this org — nobody is viewing the dashboard
    // for that org right now, so the event has nowhere to go. The next
    // client to join will pull the org-snapshot HTTP route and pick up
    // current state; ephemeral events like dev_activity are not replayed.
    console.log(
      `[BridgeEndpoint] drop type=${safeLog(payload.type)} org=${safeLog(payload.orgId)} ` +
      `reason=no_active_room registered=[${[...orgRooms.keys()].map(safeLog).join(",")}]`,
    )
    res.status(200).json({ delivered: false, reason: "no active room" })
    return
  }

  console.log(
    `[BridgeEndpoint] deliver type=${safeLog(payload.type)} org=${safeLog(payload.orgId!)}`,
  )
  try {
    room.handleBridgeEvent(payload.type, payload.data)
    res.status(200).json({ delivered: true })
  } catch (err) {
    console.error(`[BridgeEndpoint] Error handling event type=${payload.type}:`, err)
    res.status(500).json({ error: "internal error" })
  }
}

/**
 * Dispatch a room-scoped event. Returns `true` if the response has been
 * sent (always — caller bails out either way). Centralised here so the
 * per-event routing table stays in one place as new room-scoped events
 * are added.
 */
function dispatchRoomScoped(payload: BridgePayload, res: Response): true {
  const roomId = payload.roomId!
  const data = payload.data ?? {}
  if (payload.type === "race_invite_declined") {
    const userId = typeof data.userId === "string" ? data.userId : null
    if (!userId) {
      res.status(400).json({ error: "race_invite_declined needs userId" })
      return true
    }
    fireRaceInviteDeclined(roomId, userId)
    res.status(200).json({ delivered: true })
    return true
  }
  if (payload.type === "backlash_invite_declined") {
    const userId = typeof data.userId === "string" ? data.userId : null
    if (!userId) {
      res.status(400).json({ error: "backlash_invite_declined needs userId" })
      return true
    }
    const delivered = fireBacklashInviteDeclined(roomId, userId)
    res.status(200).json({ delivered })
    return true
  }
  res.status(400).json({
    error: `unknown room-scoped event type: ${safeLog(payload.type)}`,
  })
  return true
}
