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
 * Test harness for a room join, replayed the way Colyseus runs it: the
 * static onAuth before matchmaking, then the room's onJoin with the identity
 * it returned (Colyseus skips any instance onAuth once the static one ran).
 */
import type { Client } from "colyseus"
import { vi } from "vitest"
import { authenticateJoin } from "../auth/roomAuth"
import type { JoinIdentity } from "../auth/verifyJoin"

/** Any room's onJoin, as the harness calls it. */
interface Joinable {
  onJoin(client: Client, options: Record<string, unknown>, auth?: JoinIdentity): unknown
}

/** A client stand-in with a session id and a recorded `send`. */
export function fakeClient(sessionId = "s1"): Client {
  return { sessionId, userData: undefined, send: vi.fn() } as unknown as Client
}

/** Join `room` with these raw options: the static onAuth, then onJoin with its result. */
export async function joinRoom(
  room: Joinable,
  client: Client,
  options: Record<string, unknown>,
): Promise<void> {
  const auth = await authenticateJoin(undefined, options)
  await room.onJoin(client, options, auth)
}
