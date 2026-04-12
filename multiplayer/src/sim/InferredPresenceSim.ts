/**
 * InferredPresenceSim — derive pseudo-presence from dev activity + clock.
 *
 * When a user is not Slack-driven (no slack_id, or org has no Slack bot
 * token), we have no real presence signal. This sim fills the gap by
 * inferring "where should their character be?" from:
 *
 *   - dev activity history (first event today, last event)
 *   - time of day (working hours, lunch, evening)
 *   - day of week (working day vs off day)
 *
 * The result is a triple of (presence, preferred-break-zone, now) that
 * `OrgRoom.applyPresenceChange` consumes to drive the same walk-home
 * machinery Slack-driven presence uses. No new placement path is needed.
 *
 * Inferred rules (authoritative):
 *
 *   1. Non-working day (per org config)                 → at_home  (bed)
 *   2. Outside working hours                            → at_home  (bed)
 *   3. Past morningGrace, ZERO activity today           → on_break (pool_resort)
 *   4. In working hours, active within idle threshold   → active   (desk)
 *   5. In working hours, idle over idle threshold       → on_break (cafeteria)
 *   6. Before morningGrace, no activity yet             → active   (desk, grace period)
 *
 * Idle threshold defaults:
 *   - Normal hours:  10 minutes
 *   - Lunch hours:   20 minutes (more forgiving — lingering at lunch is expected)
 *
 * Per-org config (working days, hours, timezone, auto-mode toggle) flows
 * from the backend via the org-snapshot bridge. See `./PresenceConfig.ts`
 * for the normalised config type, defaults, builder, and timezone-aware
 * time extraction. This file is intentionally focused on the rules
 * engine + trace tracking — anything config-shaped lives next door.
 *
 * The `evaluate()` method is a pure function: it takes a trace, a `now`
 * Date, and an optional config, returns a result. No side effects, no
 * `Date.now()` — all time comes from the caller. This makes it trivially
 * unit-testable without timer mocks.
 */
import type { MemberState } from "../schema/MemberState"
import type { PresenceState } from "./MemberPlacement"
import {
  DEFAULT_PRESENCE_CONFIG,
  extractLocalTimeParts,
  type PresenceConfig,
} from "./PresenceConfig"

// Re-export config symbols so consumers can keep importing from this
// module without learning about the split. Tests and OrgRoom both
// reach for `buildPresenceConfig` — expose it transparently.
export {
  DEFAULT_PRESENCE_CONFIG,
  buildPresenceConfig,
  type PresenceConfig,
} from "./PresenceConfig"

/** Idle threshold for cafeteria routing, in minutes. */
const IDLE_THRESHOLD_NORMAL_MIN = 10
const IDLE_THRESHOLD_LUNCH_MIN = 20

// ─── Types ───────────────────────────────────

/** Per-member dev-activity history tracked by the sim. */
export interface DevActivityTrace {
  /** First dev_activity of the current day. Null if no activity yet today. */
  firstAt: Date | null
  /** Most recent dev_activity. Null if never active. */
  lastAt: Date | null
  /** `YYYY-MM-DD` in the org's configured timezone — used for day-rollover detection. */
  lastAtDayKey: string
}

/** Result of the rules engine — what presence should this member be in? */
export interface InferredResult {
  presence: PresenceState
  /**
   * Optional preferred break zone. Only meaningful when `presence === "on_break"`.
   * `computePlacement` honors this as a first-pass hint.
   */
  preferredZone?: string
}

/**
 * Callback used by `tick` to apply an inferred presence change. OrgRoom
 * wires this to its own `applyPresenceChange(userId, presence, preferredZone)`.
 */
export type InferredPresenceCallback = (
  userId: string,
  presence: PresenceState,
  preferredZone?: string,
) => void

// ─── Sim ─────────────────────────────────────

export class InferredPresenceSim {
  /** Per-member dev-activity history. Keyed by userId. */
  private traces = new Map<string, DevActivityTrace>()

  /** Per-org presence configuration. Applied via `setConfig()`. */
  private config: PresenceConfig = DEFAULT_PRESENCE_CONFIG

  /**
   * @param onPresenceChange Called on every tick for every member whose
   *   inferred presence differs from their current state. Typically wired
   *   to `OrgRoom.applyPresenceChange`.
   */
  constructor(private readonly onPresenceChange: InferredPresenceCallback) {}

  /**
   * Swap in a new org-level presence configuration. Called by OrgRoom
   * after a snapshot fetch (both initial and 15-minute refresh). Reset
   * of in-flight traces is deliberately NOT performed so dev activity
   * recorded while auto mode was off still counts when it comes back on.
   */
  setConfig(config: PresenceConfig): void {
    this.config = config
  }

  /**
   * Record a dev_activity event for a member. Called from OrgRoom's
   * `dev_activity` bridge handler so the inferred sim stays in sync with
   * the dev activity sim's own state.
   *
   * Handles day rollover: if `lastAt` is from a prior day, `firstAt` is
   * reset so "first event today" tracking is accurate even across midnight.
   * The day key is computed in the org's configured timezone so a dev
   * activity event at 23:30 local time doesn't spuriously roll over at
   * UTC midnight.
   */
  recordDevActivity(userId: string, now: Date): void {
    const { dayKey } = extractLocalTimeParts(now, this.config.timezone)
    const existing = this.traces.get(userId)
    if (!existing || existing.lastAtDayKey !== dayKey) {
      // New day (or never seen) → this event is the first today
      this.traces.set(userId, {
        firstAt:      now,
        lastAt:       now,
        lastAtDayKey: dayKey,
      })
      return
    }
    // Same day → update lastAt only
    existing.lastAt = now
    existing.lastAtDayKey = dayKey
  }

  /**
   * Drop all tracked traces. Called on snapshot reload to avoid acting on
   * stale day-key data when the server restarts or the members list changes.
   */
  reset(): void {
    this.traces.clear()
  }

  /**
   * Evaluate every member's inferred presence and fire `onPresenceChange`
   * for anyone whose inferred state differs from their current `member.presence`.
   *
   * Skips:
   *   - When `config.autoModeEnabled === false` (short-circuits the whole
   *     loop; members stay wherever takeover/manual placement put them).
   *   - Members with `takeoverSessionId !== ""` (player control wins)
   *   - Members in `hasSlack` (Slack-driven; Phase B handles them)
   *
   * `now` is passed in rather than read from `Date.now()` so tests can
   * drive exact time points. The tick interval is not fixed — caller
   * decides how often to run (typically 60 seconds).
   */
  tick(
    members: Map<string, MemberState>,
    hasSlack: Set<string>,
    now: Date,
  ): void {
    // Auto mode off → never touch any member. Dev activity traces still
    // update via recordDevActivity so flipping auto mode back on is warm.
    if (!this.config.autoModeEnabled) return

    for (const [userId, member] of members) {
      if (member.takeoverSessionId) continue
      if (hasSlack.has(userId)) continue

      const result = InferredPresenceSim.evaluate(
        this.traces.get(userId),
        now,
        this.config,
      )
      if (result.presence === member.presence) continue

      // Only fire the change if the DISPLAY state actually differs.
      // applyPresenceChange is idempotent, but skipping here keeps the
      // tick log cleaner and avoids a redundant callback invocation.
      this.onPresenceChange(userId, result.presence, result.preferredZone)
    }
  }

  /**
   * Pure rules engine — no side effects, no clock reads. Takes a trace,
   * a `now` Date, and an optional config; returns what presence the
   * member should be in.
   *
   * The `config` parameter defaults to `DEFAULT_PRESENCE_CONFIG` (which
   * has `timezone: undefined`), so legacy callers that pass only a trace
   * and a `now` get the exact hardcoded behaviour that existed before
   * this function became configurable — no test rewrites required.
   *
   * Static so tests can call it directly without constructing a sim.
   */
  static evaluate(
    trace: DevActivityTrace | undefined,
    now: Date,
    config: PresenceConfig = DEFAULT_PRESENCE_CONFIG,
  ): InferredResult {
    const { dow, hour, dayKey } = extractLocalTimeParts(now, config.timezone)

    // Rule 1: non-working day → at_home
    if (!config.workingDays.has(dow)) {
      return { presence: "at_home" }
    }

    // Rule 2: outside working hours → at_home
    if (hour < config.workingHoursStart || hour >= config.workingHoursEnd) {
      return { presence: "at_home" }
    }

    // Trace may be missing (never active) or from a prior day (stale)
    const sameDayTrace =
      trace && trace.lastAtDayKey === dayKey ? trace : undefined
    const hasActivityToday = sameDayTrace?.firstAt != null

    // Rule 3: past morning grace with zero activity today → pool (slacking off)
    if (hour >= config.morningGraceHour && !hasActivityToday) {
      return { presence: "on_break", preferredZone: "pool_resort" }
    }

    // Rule 6: before grace hour with no activity yet → grace period, desk
    if (!hasActivityToday) {
      return { presence: "active" }
    }

    // Rules 4 & 5: has activity today → threshold comparison
    const lastAt = sameDayTrace!.lastAt!
    const idleMs = now.getTime() - lastAt.getTime()
    const idleMin = idleMs / 60_000
    const thresholdMin = isLunchHour(hour, config)
      ? IDLE_THRESHOLD_LUNCH_MIN
      : IDLE_THRESHOLD_NORMAL_MIN

    if (idleMin > thresholdMin) {
      return { presence: "on_break", preferredZone: "cafeteria" }
    }
    return { presence: "active" }
  }
}

// ─── Helpers ─────────────────────────────────

/** Is the given hour within the config's lunch window? */
function isLunchHour(hour: number, config: PresenceConfig): boolean {
  return hour >= config.lunchHoursStart && hour < config.lunchHoursEnd
}
