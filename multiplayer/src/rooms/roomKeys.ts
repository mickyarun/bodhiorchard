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
 * Shared rooms are matched on the keys that name their owner (see
 * `roomDefinitions.ts`). A room created without one would belong to nobody:
 * `joinOrCreate` treats a missing filter key as "any value", so such a room
 * would collect joins meant for other owners. Creation refuses instead.
 */

/** The non-empty string `key` from a room's create options, or a refusal. */
export function requireRoomKey(options: unknown, key: string): string {
  const value =
    typeof options === "object" && options !== null
      ? (options as Record<string, unknown>)[key]
      : undefined
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`room needs its ${key}`)
  }
  return value
}
