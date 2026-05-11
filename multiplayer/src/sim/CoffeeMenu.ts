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
 * Canonical coffee drink menu — shared by client UI and server validation.
 * Used by CoffeeBarRoom to whitelist incoming coffee_enqueue messages and by
 * the frontend drink picker to render the four ordering buttons.
 */
export const COFFEE_DRINKS = ["espresso", "latte", "cappuccino", "tea"] as const
export type CoffeeDrink = typeof COFFEE_DRINKS[number]

export function isCoffeeDrink(value: unknown): value is CoffeeDrink {
  return typeof value === "string" && (COFFEE_DRINKS as readonly string[]).includes(value)
}

// Phase durations (ms). Server-side timing — clients render from phase state
// and do not drive transitions.
export const COFFEE_PHASE_MS = {
  approaching: 2500,
  brewing: 3000,
  dispensed: 4000,
} as const
