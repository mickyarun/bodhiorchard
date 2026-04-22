// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
