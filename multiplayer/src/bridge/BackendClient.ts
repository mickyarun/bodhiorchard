// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * BackendClient — Colyseus → backend HTTP client.
 *
 * The Colyseus server calls the backend to:
 *   - Fetch initial org snapshot when an OrgRoom is created
 *   - Verify user JWTs on room join
 *
 * Shared secret authentication via X-Bridge-Secret header.
 */

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000"

// Fail-closed in production; allow a dev default for local tooling.
if (process.env.NODE_ENV === "production" && !process.env.COLYSEUS_BRIDGE_SECRET) {
  throw new Error(
    "[BackendClient] COLYSEUS_BRIDGE_SECRET must be set in production. " +
    "Refusing to start with the dev default secret.",
  )
}
const BRIDGE_SECRET = process.env.COLYSEUS_BRIDGE_SECRET ?? "dev-colyseus-bridge-secret"

export interface OrgSnapshotMember {
  user_id: string
  name: string
  character_model: string | null
  presence: "active" | "on_break" | "at_home"
  level?: number
  level_name?: string
  /**
   * True if this member's presence is authoritatively driven by Slack
   * (user has a slack_id AND the org has a slack_bot_token configured).
   * False means presence must be inferred from dev activity + time of day
   * via InferredPresenceSim (Phase C). Defaults to false when absent so
   * old snapshots without this field fall through to inferred presence.
   */
  has_slack?: boolean
  house_level?: number
  vehicle_unlocks?: string[]
}

/** Valid day-of-week keys for `PresenceSettingsPayload.workingDays`. */
export type WeekdayKey = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun"

/**
 * Per-org presence configuration as returned by the backend's
 * `/internal/colyseus/org-snapshot` endpoint. The camelCase naming
 * mirrors the Pydantic `PresenceSettings` schema serialised with
 * `by_alias=True`. The multiplayer side consumes this via
 * `buildPresenceConfig` which normalises it into the internal
 * `PresenceConfig` shape used by `InferredPresenceSim`.
 */
export interface PresenceSettingsPayload {
  autoModeEnabled: boolean
  workingDays: WeekdayKey[]
  workingHoursStart: string  // "HH:MM" 24-hour
  workingHoursEnd: string    // "HH:MM" 24-hour
  timezone: string | null    // null = use server local time (legacy path)
}

export interface OrgSnapshotResponse {
  orgId: string
  members: OrgSnapshotMember[]
  repos: Array<{ repo_name: string; growth_stage: number }>
  /**
   * Optional for backward compatibility — snapshots generated before
   * this field existed simply omit it, and the sim falls back to
   * `DEFAULT_PRESENCE_CONFIG` (Mon-Fri, 8-18, no timezone).
   */
  presenceSettings?: PresenceSettingsPayload
}

export interface TokenVerification {
  valid: boolean
  user_id?: string
  org_id?: string
  name?: string
  /** Reason for failure — set when valid=false to aid diagnostics. */
  reason?: "token_invalid" | "backend_http_error" | "backend_unreachable"
}

const FETCH_TIMEOUT_MS = 3000

/** Fetch an org snapshot from the backend. Returns null on failure. */
export async function fetchOrgSnapshot(orgId: string): Promise<OrgSnapshotResponse | null> {
  try {
    const url = `${BACKEND_URL}/api/v1/internal/colyseus/org-snapshot/${orgId}`
    const response = await fetch(url, {
      method: "GET",
      headers: {
        "X-Bridge-Secret": BRIDGE_SECRET,
      },
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    })
    if (!response.ok) {
      console.warn(`[BackendClient] org-snapshot failed: ${response.status} ${response.statusText}`)
      return null
    }
    return (await response.json()) as OrgSnapshotResponse
  } catch (err) {
    console.warn(`[BackendClient] org-snapshot error:`, err)
    return null
  }
}

/**
 * Persist + publish a race invitation via the backend.
 *
 * Called once per invitee when OrgRoom processes `race_create`. The
 * backend writes a `notifications` row and broadcasts on the recipient's
 * WS topic; we get the notification id back. Failures are logged but
 * don't block the race-room creation — a missed invite is recoverable
 * (user just doesn't see a toast), a missed room would be fatal.
 */
export interface RaceInvitePayload {
  orgId: string
  recipientUserId: string
  hostUserId: string
  hostName: string
  roomId: string
  distanceM: number
}

export async function postRaceInvite(payload: RaceInvitePayload): Promise<boolean> {
  try {
    const url = `${BACKEND_URL}/api/v1/internal/colyseus/race-invite`
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "X-Bridge-Secret": BRIDGE_SECRET,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    })
    if (!response.ok) {
      console.warn(`[BackendClient] race-invite HTTP ${response.status}`)
      return false
    }
    return true
  } catch (err) {
    console.warn(`[BackendClient] race-invite unreachable:`, err)
    return false
  }
}

/**
 * POST final race placings to the backend on room disposal. Idempotent
 * server-side (ON CONFLICT on `(room_id, user_id)`) so a retry after a
 * transient failure never double-counts.
 */
export interface RaceResultsPlacing {
  userId: string
  finishTimeMs: number | null
  place: number
  finished: boolean
  distanceMReached: number
  distanceM: number
}

export interface RaceResultsPayload {
  roomId: string
  orgId: string
  hostUserId: string
  distanceM: number
  placings: RaceResultsPlacing[]
}

export async function postRaceResults(payload: RaceResultsPayload): Promise<boolean> {
  try {
    const url = `${BACKEND_URL}/api/v1/internal/colyseus/race-results`
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "X-Bridge-Secret": BRIDGE_SECRET,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    })
    if (!response.ok) {
      console.warn(`[BackendClient] race-results HTTP ${response.status}`)
      return false
    }
    return true
  } catch (err) {
    console.warn(`[BackendClient] race-results unreachable:`, err)
    return false
  }
}

/** Verify a user JWT against the backend. */
export async function verifyUserToken(
  token: string,
  orgId: string,
): Promise<TokenVerification> {
  try {
    const url = `${BACKEND_URL}/api/v1/internal/colyseus/verify-token`
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "X-Bridge-Secret": BRIDGE_SECRET,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ token, org_id: orgId }),
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    })
    if (!response.ok) {
      console.warn(
        `[BackendClient] verify-token HTTP ${response.status} — ` +
        `check BACKEND_URL (${BACKEND_URL}) and COLYSEUS_BRIDGE_SECRET`,
      )
      return { valid: false, reason: "backend_http_error" }
    }
    return (await response.json()) as TokenVerification
  } catch (err) {
    console.warn(`[BackendClient] verify-token unreachable (${BACKEND_URL}):`, err)
    return { valid: false, reason: "backend_unreachable" }
  }
}
