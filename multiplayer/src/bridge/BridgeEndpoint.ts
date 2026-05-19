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

interface BridgePayload {
  orgId: string
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
  if (!payload?.orgId || !payload?.type) {
    res.status(400).json({ error: "missing orgId or type" })
    return
  }

  const room = orgRooms.get(payload.orgId)
  if (!room) {
    // No active OrgRoom for this org — nobody is viewing the dashboard
    // for that org right now, so the event has nowhere to go. The next
    // client to join will pull the org-snapshot HTTP route and pick up
    // current state; ephemeral events like dev_activity are not replayed.
    console.log(
      `[BridgeEndpoint] drop type=${payload.type} org=${payload.orgId} ` +
      `reason=no_active_room registered=[${[...orgRooms.keys()].join(",")}]`,
    )
    res.status(200).json({ delivered: false, reason: "no active room" })
    return
  }

  console.log(
    `[BridgeEndpoint] deliver type=${payload.type} org=${payload.orgId}`,
  )
  try {
    room.handleBridgeEvent(payload.type, payload.data)
    res.status(200).json({ delivered: true })
  } catch (err) {
    console.error(`[BridgeEndpoint] Error handling event type=${payload.type}:`, err)
    res.status(500).json({ error: "internal error" })
  }
}
