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
 * RaceRoom join authentication and per-client identity.
 *
 * A client's racer identity comes only from here: the JWT verified in
 * `onAuth` (or, in development without a token, the claimed join options,
 * matching OrgRoom and MinigameRoom). The `race_join` payload never chooses
 * which user a client races as, and host-only actions compare against it.
 */
import type { Client } from "colyseus"
import { verifyUserToken } from "../bridge/BackendClient"

export interface RaceJoinOptions {
  userId?: string
  name?: string
  characterModel?: string
  token?: string
}

/** Identity stored on `client.userData` once a client has joined. */
export interface RaceClientIdentity {
  userId: string
  name: string
  characterModel: string
}

/** Verify a join against the backend; the result replaces client claims. */
export async function authenticateRaceJoin(
  options: RaceJoinOptions,
  orgId: string,
): Promise<RaceJoinOptions> {
  if (!options.token) {
    if (process.env.NODE_ENV === "production") throw new Error("auth token required")
    return options
  }
  const result = await verifyUserToken(options.token, orgId)
  if (!result.valid || !result.user_id) {
    const reason = result.reason ?? "token_invalid"
    if (reason === "backend_unreachable") throw new Error("auth backend unreachable")
    if (reason === "backend_http_error") throw new Error("auth backend rejected request")
    throw new Error("invalid auth token — JWT may be expired, try refreshing the page")
  }
  if (orgId && result.org_id && result.org_id !== orgId) throw new Error("token org mismatch")
  return { ...options, userId: result.user_id, name: result.name ?? options.name }
}

/** Build the identity a joined client acts as, or null when it has none. */
export function raceIdentityFrom(options: RaceJoinOptions): RaceClientIdentity | null {
  const userId = typeof options.userId === "string" ? options.userId : ""
  if (!userId) return null
  const name = typeof options.name === "string" && options.name.trim() ? options.name.trim() : userId
  const characterModel = typeof options.characterModel === "string" ? options.characterModel : ""
  return { userId, name, characterModel }
}

/** The identity a client joined with, or null before it joined. */
export function raceIdentityOf(client: Client): RaceClientIdentity | null {
  const data = client.userData as Partial<RaceClientIdentity> | undefined
  if (!data || typeof data.userId !== "string" || !data.userId) return null
  return {
    userId: data.userId,
    name: typeof data.name === "string" && data.name ? data.name : data.userId,
    characterModel: typeof data.characterModel === "string" ? data.characterModel : "",
  }
}
