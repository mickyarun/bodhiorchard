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
 * Test harness for shared-room matchmaking. Replays what `joinOrCreate` does
 * against Colyseus's in-memory room cache (LocalDriver): store the listing a
 * room gets on creation, then look up an open room for a later join.
 */
import type { LocalDriver } from "colyseus"
import { roomDefinitions } from "../roomDefinitions"

export type SharedRoom = "org" | "coffeebar" | "cafeteria" | "house"

/** Store the listing Colyseus keeps for a room created with `options`. */
export function createListing(
  driver: LocalDriver,
  name: SharedRoom,
  roomId: string,
  options: object,
): void {
  driver.persist(
    {
      roomId,
      name,
      clients: 1,
      maxClients: 100,
      locked: false,
      private: false,
      processId: "test",
      ...roomDefinitions[name].getMetadataFromOptions(options),
    } as never,
    true,
  )
}

/** The open room a `joinOrCreate(name, options)` would land in, if any. */
export async function findOpenRoom(
  driver: LocalDriver,
  name: SharedRoom,
  options: object,
): Promise<string | undefined> {
  const found = await driver.findOne({
    locked: false,
    name,
    private: false,
    ...roomDefinitions[name].getFilterOptions(options),
  } as never)
  return found?.roomId
}
