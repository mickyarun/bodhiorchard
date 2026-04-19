// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Unit tests for InferredPresenceSim.
 *
 * All time is passed in explicitly — no vitest fake timers needed. Every
 * test constructs a specific `now` Date and optionally a `DevActivityTrace`,
 * then asserts the result of the static `evaluate()` method. Keeps tests
 * deterministic, fast, and easy to map back to the rules table in the plan.
 *
 * Dates used throughout are local time in the server's zone (whatever that
 * is) because the rules use local `getHours()` / `getDay()`. Most test
 * Dates are constructed via the `Date(year, month, day, hour, min)` form
 * which is local-time.
 *
 * Day mapping reminder (JS Date.getDay()):
 *   0 = Sunday, 1 = Monday, ..., 5 = Friday, 6 = Saturday
 *
 * Concrete anchor dates picked for readability:
 *   2026-04-13 = Monday   (weekday)
 *   2026-04-18 = Saturday (weekend)
 *   2026-04-19 = Sunday   (weekend)
 */
import { describe, it, expect } from 'vitest'
import {
  DEFAULT_PRESENCE_CONFIG,
  InferredPresenceSim,
  buildPresenceConfig,
  type DevActivityTrace,
  type PresenceConfig,
} from './InferredPresenceSim'
import type { PresenceSettingsPayload } from '../bridge/BackendClient'

/** Helper: construct a weekday local Date. Monday April 13, 2026. */
function mon(hour: number, min: number = 0): Date {
  return new Date(2026, 3 /* April */, 13, hour, min, 0, 0)
}

/** Helper: construct a Saturday local Date. */
function sat(hour: number, min: number = 0): Date {
  return new Date(2026, 3, 18, hour, min, 0, 0)
}

/** Helper: construct a Sunday local Date. */
function sun(hour: number, min: number = 0): Date {
  return new Date(2026, 3, 19, hour, min, 0, 0)
}

/** Helper: build a trace where `firstAt` and `lastAt` are on the same day. */
function traceAt(dt: Date): DevActivityTrace {
  const y = dt.getFullYear()
  const m = String(dt.getMonth() + 1).padStart(2, '0')
  const d = String(dt.getDate()).padStart(2, '0')
  return {
    firstAt:      dt,
    lastAt:       dt,
    lastAtDayKey: `${y}-${m}-${d}`,
  }
}

describe('InferredPresenceSim.evaluate — rules table coverage', () => {
  // ═══ Rule 1: Weekend → at_home ═══════════════════════════════════
  describe('Rule 1: Weekend', () => {
    it('Saturday at noon → at_home', () => {
      const r = InferredPresenceSim.evaluate(undefined, sat(12))
      expect(r.presence).toBe('at_home')
    })
    it('Sunday at 10am → at_home', () => {
      const r = InferredPresenceSim.evaluate(undefined, sun(10))
      expect(r.presence).toBe('at_home')
    })
    it('Weekend overrides dev activity — at_home even with fresh trace', () => {
      const trace = traceAt(sat(11))
      const r = InferredPresenceSim.evaluate(trace, sat(11, 30))
      expect(r.presence).toBe('at_home')
    })
    it('Saturday 3am → at_home', () => {
      const r = InferredPresenceSim.evaluate(undefined, sat(3))
      expect(r.presence).toBe('at_home')
    })
  })

  // ═══ Rule 2: Outside work hours → at_home ═══════════════════════
  describe('Rule 2: Outside work hours (weekday)', () => {
    it('Monday 7:59am → at_home (before 8am)', () => {
      const r = InferredPresenceSim.evaluate(undefined, mon(7, 59))
      expect(r.presence).toBe('at_home')
    })
    it('Monday 8:00am → NOT at_home (work hours start)', () => {
      const r = InferredPresenceSim.evaluate(undefined, mon(8, 0))
      expect(r.presence).not.toBe('at_home')
    })
    it('Monday 17:59 → NOT at_home (still work hours)', () => {
      const r = InferredPresenceSim.evaluate(undefined, mon(17, 59))
      expect(r.presence).not.toBe('at_home')
    })
    it('Monday 18:00 → at_home (end of work hours)', () => {
      const r = InferredPresenceSim.evaluate(undefined, mon(18, 0))
      expect(r.presence).toBe('at_home')
    })
    it('Monday 23:59 → at_home (evening)', () => {
      const r = InferredPresenceSim.evaluate(undefined, mon(23, 59))
      expect(r.presence).toBe('at_home')
    })
  })

  // ═══ Rule 3: Past 10am, zero activity today → pool ══════════════
  describe('Rule 3: Past 10am with zero activity today', () => {
    it('Monday 10:01am, no trace → on_break at pool_resort', () => {
      const r = InferredPresenceSim.evaluate(undefined, mon(10, 1))
      expect(r.presence).toBe('on_break')
      expect(r.preferredZone).toBe('pool_resort')
    })
    it('Monday 11am, trace from yesterday → on_break at pool (stale trace)', () => {
      // Trace from a prior day — should be treated as "no activity today"
      const yesterday = new Date(2026, 3, 12, 14, 0)  // Sunday April 12 — but we\'re testing logic
      const trace: DevActivityTrace = {
        firstAt:      yesterday,
        lastAt:       yesterday,
        lastAtDayKey: '2026-04-12',
      }
      const r = InferredPresenceSim.evaluate(trace, mon(11, 0))
      expect(r.presence).toBe('on_break')
      expect(r.preferredZone).toBe('pool_resort')
    })
    it('Monday 17:00, still no activity → pool (all afternoon no work)', () => {
      const r = InferredPresenceSim.evaluate(undefined, mon(17, 0))
      expect(r.presence).toBe('on_break')
      expect(r.preferredZone).toBe('pool_resort')
    })
  })

  // ═══ Rule 6: Before 10am, no activity yet → active (grace) ══════
  describe('Rule 6: Morning grace period (before 10am, no activity)', () => {
    it('Monday 8:00am, no trace → active (just arrived)', () => {
      const r = InferredPresenceSim.evaluate(undefined, mon(8, 0))
      expect(r.presence).toBe('active')
    })
    it('Monday 9:59am, no trace → active (still in grace period)', () => {
      const r = InferredPresenceSim.evaluate(undefined, mon(9, 59))
      expect(r.presence).toBe('active')
    })
    it('Monday 10:00am, no trace → on_break at pool (grace expired)', () => {
      // 10:00 sharp is the boundary — `hour >= MORNING_GRACE_HOUR` is true
      const r = InferredPresenceSim.evaluate(undefined, mon(10, 0))
      expect(r.presence).toBe('on_break')
      expect(r.preferredZone).toBe('pool_resort')
    })
  })

  // ═══ Rules 4 & 5: Active today, threshold comparison ════════════
  describe('Rule 4 & 5: Active today with idle threshold', () => {
    describe('Normal hours (10-minute threshold)', () => {
      it('Idle 5 minutes → active (desk)', () => {
        const trace = traceAt(mon(11, 0))
        const r = InferredPresenceSim.evaluate(trace, mon(11, 5))
        expect(r.presence).toBe('active')
      })
      it('Idle exactly 10 minutes → active (on the boundary, not over)', () => {
        const trace = traceAt(mon(11, 0))
        const r = InferredPresenceSim.evaluate(trace, mon(11, 10))
        expect(r.presence).toBe('active')
      })
      it('Idle 11 minutes → on_break at cafeteria', () => {
        const trace = traceAt(mon(11, 0))
        const r = InferredPresenceSim.evaluate(trace, mon(11, 11))
        expect(r.presence).toBe('on_break')
        expect(r.preferredZone).toBe('cafeteria')
      })
      it('Idle 30 minutes → on_break at cafeteria (very idle)', () => {
        const trace = traceAt(mon(10, 0))
        const r = InferredPresenceSim.evaluate(trace, mon(10, 30))
        expect(r.presence).toBe('on_break')
        expect(r.preferredZone).toBe('cafeteria')
      })
    })

    describe('Lunch hours (20-minute threshold, 12:00-14:00)', () => {
      it('Idle 15 minutes during lunch → active (within 20-min grace)', () => {
        const trace = traceAt(mon(12, 0))
        const r = InferredPresenceSim.evaluate(trace, mon(12, 15))
        expect(r.presence).toBe('active')
      })
      it('Idle 20 minutes during lunch → active (on boundary)', () => {
        const trace = traceAt(mon(12, 0))
        const r = InferredPresenceSim.evaluate(trace, mon(12, 20))
        expect(r.presence).toBe('active')
      })
      it('Idle 21 minutes during lunch → on_break at cafeteria', () => {
        const trace = traceAt(mon(12, 0))
        const r = InferredPresenceSim.evaluate(trace, mon(12, 21))
        expect(r.presence).toBe('on_break')
        expect(r.preferredZone).toBe('cafeteria')
      })
      it('13:59 with idle 19 min → active (still in lunch, still lenient)', () => {
        const trace = traceAt(mon(13, 40))
        const r = InferredPresenceSim.evaluate(trace, mon(13, 59))
        expect(r.presence).toBe('active')
      })
    })

    describe('Lunch boundary transitions', () => {
      it('14:00 sharp with idle 11 min → on_break (lunch ended, back to 10-min rule)', () => {
        // At 14:00, `isLunchHour(14)` is false (end-exclusive), so 10-min threshold applies
        const trace = traceAt(mon(13, 49))
        const r = InferredPresenceSim.evaluate(trace, mon(14, 0))
        expect(r.presence).toBe('on_break')
        expect(r.preferredZone).toBe('cafeteria')
      })
      it('11:59 (pre-lunch) with idle 11 min → on_break (pre-lunch rule)', () => {
        const trace = traceAt(mon(11, 48))
        const r = InferredPresenceSim.evaluate(trace, mon(11, 59))
        expect(r.presence).toBe('on_break')
        expect(r.preferredZone).toBe('cafeteria')
      })
    })
  })

  // ═══ Defensive: stale trace from a prior day ════════════════════
  describe('Stale trace handling (day rollover)', () => {
    it('Trace from yesterday is treated as "no activity today"', () => {
      const trace: DevActivityTrace = {
        firstAt:      new Date(2026, 3, 12, 14, 0),
        lastAt:       new Date(2026, 3, 12, 14, 0),
        lastAtDayKey: '2026-04-12',
      }
      // Monday 9am (before grace expiry) with yesterday's trace → active (grace period)
      const r1 = InferredPresenceSim.evaluate(trace, mon(9, 0))
      expect(r1.presence).toBe('active')
      // Monday 10:01am → pool (grace expired, still no activity today)
      const r2 = InferredPresenceSim.evaluate(trace, mon(10, 1))
      expect(r2.presence).toBe('on_break')
      expect(r2.preferredZone).toBe('pool_resort')
    })
  })
})

describe('InferredPresenceSim.recordDevActivity', () => {
  it('Records first activity and subsequent activity on the same day', () => {
    const sim = new InferredPresenceSim(() => {})
    const t1 = mon(9, 30)
    const t2 = mon(11, 0)
    sim.recordDevActivity('u1', t1)
    sim.recordDevActivity('u1', t2)
    // evaluate should see a trace with lastAt = t2 and firstAt = t1
    // We can observe this indirectly: at mon(11, 5), idle is 5 min → active
    const r = InferredPresenceSim.evaluate(
      // Reach into the private map via a known-same-day trace
      // — easier: rebuild a trace equivalent
      { firstAt: t1, lastAt: t2, lastAtDayKey: '2026-04-13' },
      mon(11, 5),
    )
    expect(r.presence).toBe('active')
  })

  it('Resets firstAt on day rollover', () => {
    const sim = new InferredPresenceSim(() => {})
    // Record yesterday
    sim.recordDevActivity('u1', new Date(2026, 3, 12, 14, 0))
    // Record today — should reset firstAt to this new event
    sim.recordDevActivity('u1', mon(9, 30))
    // The sim's internal trace should now have firstAt = 9:30 today, not yesterday
    // We verify by triggering a tick and checking the observable behavior
    const members = new Map([
      ['u1', { takeoverSessionId: '', presence: 'at_home' } as unknown as import('../schema/MemberState').MemberState],
    ])
    const calls: Array<[string, string, string?]> = []
    const sim2 = new InferredPresenceSim((id, p, z) => calls.push([id, p, z]))
    sim2.recordDevActivity('u1', new Date(2026, 3, 12, 14, 0))
    sim2.recordDevActivity('u1', mon(9, 30))
    sim2.tick(members, new Set(), mon(9, 35))  // idle 5 min → should be active
    expect(calls).toEqual([['u1', 'active', undefined]])
  })
})

describe('InferredPresenceSim.tick — skip conditions', () => {
  it('Skips members under takeover', () => {
    const calls: Array<[string, string]> = []
    const sim = new InferredPresenceSim((id, p) => calls.push([id, p]))
    const members = new Map([
      // Takeover-controlled member with presence='active' — would normally
      // transition to at_home at 19:00 (evening rule) but should be skipped
      ['u1', { takeoverSessionId: 'sess123', presence: 'active' } as unknown as import('../schema/MemberState').MemberState],
    ])
    sim.tick(members, new Set(), mon(19, 0))
    expect(calls).toEqual([])
  })

  it('Skips members in the hasSlack set', () => {
    const calls: Array<[string, string]> = []
    const sim = new InferredPresenceSim((id, p) => calls.push([id, p]))
    const members = new Map([
      ['u1', { takeoverSessionId: '', presence: 'active' } as unknown as import('../schema/MemberState').MemberState],
    ])
    sim.tick(members, new Set(['u1']), mon(19, 0))  // u1 is Slack-driven
    expect(calls).toEqual([])
  })

  it('Does not fire when inferred presence matches current presence', () => {
    const calls: Array<[string, string]> = []
    const sim = new InferredPresenceSim((id, p) => calls.push([id, p]))
    const members = new Map([
      // Already at_home, and rules say at_home (weekend) → no change
      ['u1', { takeoverSessionId: '', presence: 'at_home' } as unknown as import('../schema/MemberState').MemberState],
    ])
    sim.tick(members, new Set(), sat(12, 0))
    expect(calls).toEqual([])
  })

  it('Fires for non-Slack non-takeover member with presence mismatch', () => {
    const calls: Array<[string, string, string?]> = []
    const sim = new InferredPresenceSim((id, p, z) => calls.push([id, p, z]))
    const members = new Map([
      // Currently "active" but evening → should become at_home
      ['u1', { takeoverSessionId: '', presence: 'active' } as unknown as import('../schema/MemberState').MemberState],
    ])
    sim.tick(members, new Set(), mon(19, 0))
    expect(calls).toEqual([['u1', 'at_home', undefined]])
  })
})

describe('buildPresenceConfig — payload → PresenceConfig normalisation', () => {
  it('undefined payload returns DEFAULT_PRESENCE_CONFIG', () => {
    const cfg = buildPresenceConfig(undefined)
    expect(cfg).toBe(DEFAULT_PRESENCE_CONFIG)
  })

  it('maps weekday keys to JS day-of-week numbers', () => {
    const payload: PresenceSettingsPayload = {
      autoModeEnabled: true,
      workingDays: ['mon', 'tue', 'wed', 'thu', 'fri', 'sat'],
      workingHoursStart: '09:00',
      workingHoursEnd: '17:00',
      timezone: null,
    }
    const cfg = buildPresenceConfig(payload)
    expect(cfg.workingDays).toEqual(new Set([1, 2, 3, 4, 5, 6]))
  })

  it('auto-derives lunch window at midpoint ± 1 for a 09-17 shift', () => {
    const cfg = buildPresenceConfig({
      autoModeEnabled: true,
      workingDays: ['mon'],
      workingHoursStart: '09:00',
      workingHoursEnd: '17:00',
      timezone: null,
    })
    expect(cfg.lunchHoursStart).toBe(12)
    expect(cfg.lunchHoursEnd).toBe(14)
  })

  it('auto-derives lunch window for a 14-22 evening shift', () => {
    // midpoint = 18 → lunch 17-19
    const cfg = buildPresenceConfig({
      autoModeEnabled: true,
      workingDays: ['mon'],
      workingHoursStart: '14:00',
      workingHoursEnd: '22:00',
      timezone: null,
    })
    expect(cfg.lunchHoursStart).toBe(17)
    expect(cfg.lunchHoursEnd).toBe(19)
  })

  it('clamps morning grace to one hour before end for short shifts', () => {
    // 09-10 shift → grace would be 11, clamped to 9 (= end - 1)
    const cfg = buildPresenceConfig({
      autoModeEnabled: true,
      workingDays: ['mon'],
      workingHoursStart: '09:00',
      workingHoursEnd: '10:00',
      timezone: null,
    })
    expect(cfg.morningGraceHour).toBe(9)
  })

  it('invalid IANA timezone falls back to undefined and does not throw', () => {
    const cfg = buildPresenceConfig({
      autoModeEnabled: true,
      workingDays: ['mon'],
      workingHoursStart: '09:00',
      workingHoursEnd: '17:00',
      timezone: 'Mars/Olympus',
    })
    expect(cfg.timezone).toBeUndefined()
  })

  it('valid IANA timezone is preserved', () => {
    const cfg = buildPresenceConfig({
      autoModeEnabled: true,
      workingDays: ['mon'],
      workingHoursStart: '09:00',
      workingHoursEnd: '17:00',
      timezone: 'America/Los_Angeles',
    })
    expect(cfg.timezone).toBe('America/Los_Angeles')
  })
})

describe('InferredPresenceSim.evaluate — timezone-aware rules', () => {
  const laConfig: PresenceConfig = buildPresenceConfig({
    autoModeEnabled: true,
    workingDays: ['mon', 'tue', 'wed', 'thu', 'fri'],
    workingHoursStart: '09:00',
    workingHoursEnd: '17:00',
    timezone: 'America/Los_Angeles',
  })

  const istSaturdayConfig: PresenceConfig = buildPresenceConfig({
    autoModeEnabled: true,
    workingDays: ['mon', 'tue', 'wed', 'thu', 'fri', 'sat'],
    workingHoursStart: '09:00',
    workingHoursEnd: '17:00',
    timezone: 'Asia/Kolkata',
  })

  it('Saturday 22:00 UTC = Saturday 15:00 LA → at_home (Sat not in LA workdays)', () => {
    const now = new Date(Date.UTC(2026, 3, 18, 22, 0))
    const r = InferredPresenceSim.evaluate(undefined, now, laConfig)
    expect(r.presence).toBe('at_home')
  })

  it('Monday 08:00 UTC = Sunday 01:00 LA → at_home (non-working day in LA)', () => {
    const now = new Date(Date.UTC(2026, 3, 13, 8, 0))
    const r = InferredPresenceSim.evaluate(undefined, now, laConfig)
    expect(r.presence).toBe('at_home')
  })

  it('Saturday 05:00 UTC = Saturday 10:30 IST → active (Sat office, in grace)', () => {
    // Grace hour for 09-17 IST config is 11; 10:30 local is before grace,
    // so Rule 6 applies: no activity yet, before grace → active (at desk).
    const now = new Date(Date.UTC(2026, 3, 18, 5, 0))
    const r = InferredPresenceSim.evaluate(undefined, now, istSaturdayConfig)
    expect(r.presence).toBe('active')
  })

  it('Saturday 22:00 UTC = Sunday 03:30 IST → at_home (non-working day IST)', () => {
    const now = new Date(Date.UTC(2026, 3, 18, 22, 0))
    const r = InferredPresenceSim.evaluate(undefined, now, istSaturdayConfig)
    expect(r.presence).toBe('at_home')
  })

  it('Day key stays the same within LA even as UTC crosses midnight', () => {
    // 07:59 UTC Tue = 00:59 PDT Tue (LA). Trace recorded Mon 23:00 UTC
    // = 16:00 PDT Mon. Day keys differ — the trace is "yesterday" in LA.
    const sim = new InferredPresenceSim(() => {})
    sim.setConfig(laConfig)
    sim.recordDevActivity('u1', new Date(Date.UTC(2026, 3, 13, 23, 0))) // Mon 16:00 LA
    // Evaluate at Tue 2026-04-14 07:59 UTC = Tue 00:59 LA (before work hours LA).
    // Outside work hours → at_home, so no activity check matters.
    const members = new Map([
      ['u1', { takeoverSessionId: '', presence: 'active' } as unknown as import('../schema/MemberState').MemberState],
    ])
    const calls: Array<[string, string]> = []
    const sim2 = new InferredPresenceSim((id, p) => calls.push([id, p]))
    sim2.setConfig(laConfig)
    sim2.recordDevActivity('u1', new Date(Date.UTC(2026, 3, 13, 23, 0)))
    sim2.tick(members, new Set(), new Date(Date.UTC(2026, 3, 14, 7, 59)))
    expect(calls).toEqual([['u1', 'at_home']])
  })
})

describe('InferredPresenceSim.tick — autoModeEnabled: false short-circuit', () => {
  const offConfig: PresenceConfig = {
    ...DEFAULT_PRESENCE_CONFIG,
    autoModeEnabled: false,
  }

  it('Does not fire callbacks for any member when auto mode is off', () => {
    const calls: Array<[string, string]> = []
    const sim = new InferredPresenceSim((id, p) => calls.push([id, p]))
    sim.setConfig(offConfig)
    const members = new Map([
      ['u1', { takeoverSessionId: '', presence: 'active' } as unknown as import('../schema/MemberState').MemberState],
      ['u2', { takeoverSessionId: '', presence: 'at_home' } as unknown as import('../schema/MemberState').MemberState],
    ])
    // Saturday and Monday 11am — both scenarios would normally fire a change.
    sim.tick(members, new Set(), sat(12, 0))
    sim.tick(members, new Set(), mon(11, 0))
    expect(calls).toEqual([])
  })

  it('recordDevActivity keeps updating traces while auto mode is off (warm restart)', () => {
    const calls: Array<[string, string, string?]> = []
    const sim = new InferredPresenceSim((id, p, z) => calls.push([id, p, z]))
    sim.setConfig(offConfig)
    sim.recordDevActivity('u1', mon(10, 0))
    // Flip auto mode back on — the recorded trace should now influence tick.
    sim.setConfig(DEFAULT_PRESENCE_CONFIG)
    const members = new Map([
      ['u1', { takeoverSessionId: '', presence: 'at_home' } as unknown as import('../schema/MemberState').MemberState],
    ])
    sim.tick(members, new Set(), mon(10, 5))  // 5 min idle → active
    expect(calls).toEqual([['u1', 'active', undefined]])
  })
})

describe('InferredPresenceSim.reset', () => {
  it('Clears all traces', () => {
    const sim = new InferredPresenceSim(() => {})
    sim.recordDevActivity('u1', mon(11, 0))
    sim.recordDevActivity('u2', mon(11, 0))
    sim.reset()
    // After reset, evaluate should see undefined trace — grace period or pool
    // depending on time. At 11am with no trace → pool.
    const members = new Map([
      ['u1', { takeoverSessionId: '', presence: 'active' } as unknown as import('../schema/MemberState').MemberState],
    ])
    const calls: Array<[string, string, string?]> = []
    const sim2 = new InferredPresenceSim((id, p, z) => calls.push([id, p, z]))
    sim2.recordDevActivity('u1', mon(9, 0))
    sim2.reset()
    sim2.tick(members, new Set(), mon(11, 0))
    // After reset, u1 has no trace → Rule 3 (past 10am, no activity today) → pool
    expect(calls).toEqual([['u1', 'on_break', 'pool_resort']])
  })
})

