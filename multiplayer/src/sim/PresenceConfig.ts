// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * PresenceConfig — normalised per-org configuration for presence rules.
 *
 * This module is the single-purpose home for everything the multiplayer
 * side needs to translate raw per-org settings (working days, hours,
 * timezone, auto-mode toggle) into a shape the rules engine can consume.
 * Kept separate from `InferredPresenceSim.ts` so:
 *
 *   * The sim class stays focused on the rules engine itself.
 *   * The helpers (`buildPresenceConfig`, `extractLocalTimeParts`) can be
 *     reused by any future multiplayer system that needs time-of-day or
 *     day-of-week awareness — e.g. a scheduled maintenance banner, a
 *     per-org agent spawn rule, a cafeteria meal-time transition.
 *   * Tests can import the helpers without constructing a sim.
 *
 * Timezone handling is intentionally "fast path for undefined, IANA path
 * otherwise" so existing sim tests (which construct dates via local-time
 * `new Date(y, m, d, h, min)` constructors) keep passing unchanged when
 * they don't pass a config. See `extractLocalTimeParts` for the rationale.
 */
import type { PresenceSettingsPayload, WeekdayKey } from "../bridge/BackendClient"

/**
 * Normalised per-org presence configuration as consumed by the sim.
 *
 * Produced from the raw snapshot payload via `buildPresenceConfig`.
 * Working hours are stored as whole hours (minutes are floored in MVP —
 * documented in the settings UI). A `timezone` of `undefined` means
 * "use server-local time", which is the fast path for legacy tests and
 * un-migrated rooms.
 */
export interface PresenceConfig {
  autoModeEnabled: boolean
  /** JS Date convention: 0=Sun..6=Sat. */
  workingDays: Set<number>
  workingHoursStart: number
  workingHoursEnd: number
  /** IANA timezone name, or `undefined` for server-local fast path. */
  timezone: string | undefined
  /** Auto-derived: `min(workingHoursStart + 2, workingHoursEnd - 1)`. */
  morningGraceHour: number
  /** Auto-derived: midpoint of working hours - 1. */
  lunchHoursStart: number
  /** Auto-derived: midpoint of working hours + 1. */
  lunchHoursEnd: number
}

/**
 * Defaults mirror the legacy hardcoded constants verbatim. Critically
 * `timezone` is `undefined` so `extractLocalTimeParts` takes the legacy
 * `getDay()`/`getHours()` path — every existing sim test passes unchanged.
 */
export const DEFAULT_PRESENCE_CONFIG: PresenceConfig = {
  autoModeEnabled: true,
  workingDays: new Set([1, 2, 3, 4, 5]),
  workingHoursStart: 8,
  workingHoursEnd: 18,
  timezone: undefined,
  morningGraceHour: 10,
  lunchHoursStart: 12,
  lunchHoursEnd: 14,
}

/** Lowercase 3-letter day key → JS `Date.getDay()` index. */
const WEEKDAY_KEY_TO_DOW: Record<WeekdayKey, number> = {
  sun: 0, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6,
}

/**
 * Build a `PresenceConfig` from a raw snapshot payload. Used by
 * `OrgRoom` when it receives (or refreshes) an org snapshot.
 *
 *   * Returns `DEFAULT_PRESENCE_CONFIG` on missing payload.
 *   * Floors `HH:MM` to whole hours (minutes are ignored for now).
 *   * Validates the timezone by attempting to construct an
 *     `Intl.DateTimeFormat`. An invalid IANA name falls back to
 *     `undefined` and logs a warning (belt-and-suspenders — the
 *     backend Pydantic schema is the primary gate).
 *   * Auto-derives `morningGraceHour` and the lunch window so
 *     non-standard shifts (e.g. 14:00-22:00) still get sensible
 *     defaults.
 */
export function buildPresenceConfig(
  payload: PresenceSettingsPayload | undefined,
): PresenceConfig {
  if (!payload) return DEFAULT_PRESENCE_CONFIG

  const start = parseInt(payload.workingHoursStart.split(":")[0]!, 10)
  const end = parseInt(payload.workingHoursEnd.split(":")[0]!, 10)
  const midpoint = Math.floor((start + end) / 2)

  let timezone: string | undefined = undefined
  if (payload.timezone) {
    try {
      // Construction throws on invalid IANA names.
      new Intl.DateTimeFormat("en-US", { timeZone: payload.timezone })
      timezone = payload.timezone
    } catch (_err) {
      console.warn(
        `[PresenceSim] Invalid IANA timezone "${payload.timezone}" — ` +
          `falling back to server-local time`,
      )
    }
  }

  const workingDays = new Set<number>()
  for (const key of payload.workingDays) {
    const dow = WEEKDAY_KEY_TO_DOW[key]
    if (dow !== undefined) workingDays.add(dow)
  }

  // Defensive: empty workingDays would mean every day is non-working,
  // putting all members permanently to bed with no visible error.
  if (workingDays.size === 0) {
    console.error(
      `[PresenceConfig] workingDays empty after mapping payload ` +
        `${JSON.stringify(payload.workingDays)} — using default Mon-Fri`,
    )
    return DEFAULT_PRESENCE_CONFIG
  }

  return {
    autoModeEnabled: payload.autoModeEnabled,
    workingDays,
    workingHoursStart: start,
    workingHoursEnd: end,
    timezone,
    // Clamp grace to one hour before end so a 09:00-10:00 shift still
    // has a usable grace window (grace = 9, end = 10 → grace < end).
    morningGraceHour: Math.min(start + 2, end - 1),
    lunchHoursStart: midpoint - 1,
    lunchHoursEnd: midpoint + 1,
  }
}

// ─── Timezone-aware time extraction ───────────────────────────────────

/**
 * Cache of `Intl.DateTimeFormat` instances keyed by IANA timezone.
 * Constructing a formatter is not free; reusing one per tick is cheap.
 */
const FORMATTER_CACHE = new Map<string, Intl.DateTimeFormat>()

/** `Intl.DateTimeFormat` weekday "short" → JS `Date.getDay()` index. */
const WEEKDAY_SHORT_TO_DOW: Record<string, number> = {
  Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6,
}

/**
 * Extract the local day-of-week, hour, and YYYY-MM-DD day key for
 * `now` in the given timezone. `undefined` timezone takes the legacy
 * `getDay()`/`getHours()` fast path that preserves pre-config behaviour.
 *
 * The `en-CA` locale is chosen for its ISO-like date part ordering,
 * and `weekday: "short"` is deterministic for `en-US`/`en-CA`. The
 * `hourCycle: "h23"` avoids the "24" vs "00" midnight quirk.
 */
export function extractLocalTimeParts(
  now: Date,
  timezone: string | undefined,
): { dow: number; hour: number; dayKey: string } {
  if (!timezone) {
    return {
      dow: now.getDay(),
      hour: now.getHours(),
      dayKey: dayKeyOfLocal(now),
    }
  }
  let fmt = FORMATTER_CACHE.get(timezone)
  if (!fmt) {
    fmt = new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      weekday: "short",
      hour: "2-digit",
      hourCycle: "h23",
    })
    FORMATTER_CACHE.set(timezone, fmt)
  }
  const parts = fmt.formatToParts(now)
  const get = (type: Intl.DateTimeFormatPartTypes): string =>
    parts.find((p) => p.type === type)?.value ?? ""

  const weekdayShort = get("weekday")
  const dow = WEEKDAY_SHORT_TO_DOW[weekdayShort] ?? now.getDay()
  const hour = parseInt(get("hour"), 10)
  // Reassemble YYYY-MM-DD from the ISO-like en-CA parts.
  const dayKey = `${get("year")}-${get("month")}-${get("day")}`
  return { dow, hour, dayKey }
}

/**
 * Server-local `YYYY-MM-DD` day key. Only used by the legacy fast path
 * in `extractLocalTimeParts` when no timezone is configured.
 */
function dayKeyOfLocal(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, "0")
  const day = String(d.getDate()).padStart(2, "0")
  return `${y}-${m}-${day}`
}
