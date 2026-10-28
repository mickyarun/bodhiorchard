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
 * RaceRoom per-client identity.
 *
 * A client's racer identity comes only from the join the static `onAuth`
 * accepted (the token's user), and only when that user is in the race's org.
 * The `race_join` payload never chooses which user a client races as, and
 * host-only actions compare against this identity.
 */
import type { Client } from "colyseus"
import type { JoinCredentials, JoinIdentity } from "../auth/verifyJoin"
import { requireRoomIdentity } from "../auth/roomAuth"

export interface RaceJoinOptions extends JoinCredentials {
  characterModel?: string
}

/** Identity stored on `client.userData` once a client has joined. */
export interface RaceClientIdentity {
  userId: string
  name: string
  characterModel: string
}

/**
 * The identity a joined client acts as: the verified user, plus the avatar
 * it asked for (cosmetic). Refuses a join that did not pass onAuth, or whose
 * verified org is not the race's.
 */
export function raceIdentityFrom(
  auth: JoinIdentity | undefined,
  options: RaceJoinOptions,
  raceOrgId: string,
): RaceClientIdentity {
  const { userId, name } = requireRoomIdentity(auth, raceOrgId)
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
