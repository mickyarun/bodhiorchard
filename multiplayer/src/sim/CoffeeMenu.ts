// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
