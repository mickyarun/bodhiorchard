/**
 * Shared number formatting utilities.
 */

/** Format skill points: show integers without decimals, fractional with 2 places. */
export function formatSP(sp: number): string {
  return Number.isInteger(sp) ? sp.toString() : sp.toFixed(2)
}
