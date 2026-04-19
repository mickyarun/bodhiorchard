// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Shared number formatting utilities.
 */

/** Format skill points: show integers without decimals, fractional with 2 places. */
export function formatSP(sp: number): string {
  return Number.isInteger(sp) ? sp.toString() : sp.toFixed(2)
}
