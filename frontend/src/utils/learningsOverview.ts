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
 * Pure shaping for the Learnings page: the headline numbers, the
 * per-stage day breakdown for each complexity and the weekly shipped
 * series. Everything is derived from ``GET /v1/learnings/overview``.
 */
import type {
  ComplexityBucket,
  RepeatOffender,
  VelocityTrendPoint,
} from '@/composables/useLearningsOverview'
import { BUD_STATUS_COLORS, BUD_STATUS_LABELS, BUD_STATUS_ORDER, type BUDStatus } from '@/types'

/** The backend's velocity window (``VELOCITY_TREND_WEEKS``). */
export const TREND_WEEKS = 12

const DAY_MS = 86_400_000

export interface StagePart {
  phase: string
  label: string
  color: string
  days: number
}

export interface StageRow {
  complexity: number
  samples: number
  parts: StagePart[]
  totalDays: number
}

export interface WeekBar {
  weekStart: string
  label: string
  shipped: number
  avgCycleDays: number | null
}

export interface LearningsKpi {
  label: string
  value: string
  sub: string
}

function isStage(phase: string): phase is BUDStatus {
  return (BUD_STATUS_ORDER as string[]).includes(phase)
}

export function stageLabel(phase: string): string {
  return isStage(phase) ? BUD_STATUS_LABELS[phase] : phase.replace(/_/g, ' ')
}

/** Theme colour for a stage; unknown phases fall back to muted. */
export function stageColor(phase: string): string {
  return isStage(phase) ? BUD_STATUS_COLORS[phase] : 'muted'
}

function lifecycleIndex(phase: string): number {
  const i = (BUD_STATUS_ORDER as string[]).indexOf(phase)
  return i === -1 ? BUD_STATUS_ORDER.length : i
}

export function formatDays(days: number | null): string {
  return days == null ? '–' : `${days.toFixed(1)}d`
}

/** Median of the weekly average cycle times, or null with no closures. */
export function medianCycle(points: VelocityTrendPoint[]): number | null {
  if (points.length === 0) return null
  const sorted = points.map(p => p.avg_cycle_days).sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
}

export function shippedTotal(points: VelocityTrendPoint[]): number {
  return points.reduce((sum, p) => sum + p.n_buds, 0)
}

/** Median days per stage for one complexity, in lifecycle order. */
export function stageRow(bucket: ComplexityBucket): StageRow {
  const parts = bucket.phases
    .filter(p => (p.p50_days ?? 0) > 0)
    .sort((a, b) => lifecycleIndex(a.phase) - lifecycleIndex(b.phase))
    .map(p => ({ phase: p.phase, label: stageLabel(p.phase), color: stageColor(p.phase), days: p.p50_days ?? 0 }))
  const totalDays = parts.reduce((sum, p) => sum + p.days, 0)
  return { complexity: bucket.complexity, samples: bucket.n_samples_total, parts, totalDays }
}

/** Every stage that appears in any row, in lifecycle order, for the legend. */
export function stageLegend(rows: StageRow[]): StagePart[] {
  const seen = new Map<string, StagePart>()
  for (const row of rows) for (const part of row.parts) if (!seen.has(part.phase)) seen.set(part.phase, part)
  return [...seen.values()].sort((a, b) => lifecycleIndex(a.phase) - lifecycleIndex(b.phase))
}

/** The stage with the longest sample-weighted median across complexities. */
export function slowestStage(buckets: ComplexityBucket[]): { label: string; days: number } | null {
  const totals = new Map<string, { weighted: number; samples: number }>()
  for (const bucket of buckets) {
    for (const p of bucket.phases) {
      if (p.p50_days == null || p.n_samples <= 0) continue
      const t = totals.get(p.phase) ?? { weighted: 0, samples: 0 }
      t.weighted += p.p50_days * p.n_samples
      t.samples += p.n_samples
      totals.set(p.phase, t)
    }
  }
  let best: { label: string; days: number } | null = null
  for (const [phase, t] of totals) {
    const days = t.weighted / t.samples
    if (!best || days > best.days) best = { label: stageLabel(phase), days }
  }
  return best
}

/** ``YYYY-MM-DD`` of the Monday on or before ``date``, in UTC like the backend. */
export function mondayOf(date: Date): string {
  const day = (date.getUTCDay() + 6) % 7
  const monday = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()) - day * DAY_MS)
  return monday.toISOString().slice(0, 10)
}

function weekLabel(weekStart: string): string {
  return new Date(`${weekStart}T00:00:00Z`).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  })
}

/**
 * One bar per week for the trend window, oldest first, including the
 * weeks nothing shipped (the API only returns weeks with closures).
 */
export function weeklyShipped(points: VelocityTrendPoint[], today: Date, weeks = TREND_WEEKS): WeekBar[] {
  const byWeek = new Map(points.map(p => [p.week_start, p]))
  const lastMonday = Date.parse(`${mondayOf(today)}T00:00:00Z`)
  return Array.from({ length: weeks }, (_, i) => {
    const weekStart = new Date(lastMonday - (weeks - 1 - i) * 7 * DAY_MS).toISOString().slice(0, 10)
    const point = byWeek.get(weekStart)
    return {
      weekStart,
      label: weekLabel(weekStart),
      shipped: point?.n_buds ?? 0,
      avgCycleDays: point?.avg_cycle_days ?? null,
    }
  })
}

export function learningsKpis(
  points: VelocityTrendPoint[],
  buckets: ComplexityBucket[],
  offenders: RepeatOffender[],
): LearningsKpi[] {
  const median = medianCycle(points)
  const slowest = slowestStage(buckets)
  return [
    { label: 'Shipped', value: String(shippedTotal(points)), sub: `BUDs closed in the last ${TREND_WEEKS} weeks` },
    { label: 'Median cycle time', value: formatDays(median), sub: 'Per BUD, from the weekly averages' },
    {
      label: 'Slowest stage',
      value: slowest?.label ?? '–',
      sub: slowest ? `${formatDays(slowest.days)} median` : 'Needs more closed BUDs',
    },
    {
      label: 'Stages over estimate',
      value: String(offenders.length),
      sub: 'Median overrun above 30%',
    },
  ]
}
