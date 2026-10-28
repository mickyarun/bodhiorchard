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
 * The one join check every room's `onAuth` goes through.
 *
 * A join is accepted only when the client's JWT verifies against the backend
 * (`/internal/colyseus/verify-token`), the backend names both the user and
 * the org, and that org is exactly the room's org. The identity a room acts
 * on (user id, display name, org) is taken from the backend's answer alone;
 * whatever the client put in its join options is ignored.
 *
 * Tokenless joins are refused unless the operator opts in with
 * `MULTIPLAYER_ALLOW_TOKENLESS_JOIN=1`, and never when `NODE_ENV` is
 * `production`. Such a development join gets a namespaced identity,
 * `dev:<claimed userId>`, so it can never act as a real member, and it must
 * name the room's org exactly, so its claims cannot reach another org's room.
 */
import { verifyUserToken, type TokenVerification } from "../bridge/BackendClient"
import { safeLog } from "../bridge/logSanitize"

/** Env flag that lets a non-production server accept tokenless joins. */
export const TOKENLESS_JOIN_FLAG = "MULTIPLAYER_ALLOW_TOKENLESS_JOIN"
/** Prefix on every tokenless identity, so it never collides with a real user id. */
export const TOKENLESS_USER_PREFIX = "dev:"

/** What a client sends when joining. Only `token` is trusted, after verification. */
export interface JoinCredentials {
  token?: unknown
  userId?: unknown
  name?: unknown
  orgId?: unknown
}

/** The identity a room acts on once a join is accepted. */
export interface JoinIdentity {
  userId: string
  name: string
  orgId: string
}

/**
 * Accept or refuse a join to a room that belongs to `roomOrgId`.
 * Throws (which Colyseus turns into a refused join) on any doubt.
 */
export async function verifyJoin(
  options: JoinCredentials | undefined,
  roomOrgId: string,
): Promise<JoinIdentity> {
  if (!roomOrgId) throw refuse("room has no org", roomOrgId)
  const token = nonEmpty(options?.token)
  if (!token) return tokenlessIdentity(options, roomOrgId)

  const result = await verifyUserToken(token, roomOrgId)
  if (!result.valid) throw refuse(refusalMessage(result.reason), roomOrgId)
  const userId = nonEmpty(result.user_id)
  const orgId = nonEmpty(result.org_id)
  if (!userId || !orgId) throw refuse("token verification named no user or org", roomOrgId)
  if (orgId !== roomOrgId) throw refuse("token org mismatch", roomOrgId)
  return { userId, name: nonEmpty(result.name) || userId, orgId }
}

/** The identity `onAuth` returned, for `onJoin`. Refuses a join that skipped it. */
export function requireJoinIdentity(auth: JoinIdentity | undefined): JoinIdentity {
  if (!auth || !auth.userId || !auth.orgId) throw new Error("join was not verified")
  return auth
}

/** True when this process may accept a join that carries no token. */
export function tokenlessJoinAllowed(): boolean {
  return process.env[TOKENLESS_JOIN_FLAG] === "1" && process.env.NODE_ENV !== "production"
}

function tokenlessIdentity(
  options: JoinCredentials | undefined,
  roomOrgId: string,
): JoinIdentity {
  if (!tokenlessJoinAllowed()) throw refuse("auth token required", roomOrgId)
  const claimedUser = nonEmpty(options?.userId)
  if (!claimedUser) throw refuse("tokenless join needs a userId", roomOrgId)
  if (nonEmpty(options?.orgId) !== roomOrgId) {
    throw refuse("tokenless join org mismatch", roomOrgId)
  }
  const userId = `${TOKENLESS_USER_PREFIX}${claimedUser}`
  console.warn(
    `[verifyJoin] tokenless development join user=${safeLog(userId)} org=${safeLog(roomOrgId)}`,
  )
  return { userId, name: nonEmpty(options?.name) || userId, orgId: roomOrgId }
}

/** Log a refused join (the reason is server-chosen text) and build its error. */
function refuse(reason: string, roomOrgId: string): Error {
  console.warn(`[verifyJoin] join refused org=${safeLog(roomOrgId)} reason=${reason}`)
  return new Error(reason)
}

function refusalMessage(reason: TokenVerification["reason"]): string {
  if (reason === "backend_unreachable") {
    return "auth backend unreachable — is the Python server running?"
  }
  if (reason === "backend_http_error") {
    return "auth backend rejected request — check bridge secret and endpoint URL"
  }
  return "invalid auth token — JWT may be expired, try refreshing the page"
}

function nonEmpty(value: unknown): string {
  return typeof value === "string" ? value.trim() : ""
}
