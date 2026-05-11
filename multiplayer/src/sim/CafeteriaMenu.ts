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
 * Canonical cafeteria meal menu — shared by client UI and server validation.
 * Used by CafeteriaRoom to whitelist incoming cafe_enqueue messages and by the
 * frontend food picker to render the ordering buttons.
 */
export const CAFETERIA_MEALS = ["sandwich", "salad", "curry", "pizza", "ramen"] as const
export type CafeteriaMeal = typeof CAFETERIA_MEALS[number]

export function isCafeteriaMeal(value: unknown): value is CafeteriaMeal {
  return typeof value === "string" && (CAFETERIA_MEALS as readonly string[]).includes(value)
}

// Phase durations (ms). Server-side timing — clients render from phase state
// and do not drive transitions. Cooking runs slightly longer than brewing to
// feel distinct from the coffee bar.
export const CAFETERIA_PHASE_MS = {
  approaching: 2500,
  cooking: 4000,
  dispensed: 4000,
} as const
