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


import { describe, expect, it } from 'vitest'
import type { ComplexityBucket, PhaseRollup } from '@/composables/useLearningsOverview'
import {
  formatDays,
  learningsKpis,
  medianCycle,
  mondayOf,
  shippedTotal,
  slowestStage,
  stageLegend,
  stageRow,
  weeklyShipped,
} from './learningsOverview'

function phase(name: string, p50: number | null, n = 2): PhaseRollup {
  return { phase: name, n_samples: n, p50_days: p50, p70_days: null, p85_days: null, running_mean: null, trend_30d_pct: null }
}

const simple: ComplexityBucket = {
  complexity: 1,
  n_samples_total: 4,
  phases: [phase('testing', 1), phase('development', 2), phase('code_review', 0), phase('bud', 0.5)],
}
const complex: ComplexityBucket = {
  complexity: 5,
  n_samples_total: 2,
  phases: [phase('code_review', 4.5, 1), phase('development', 7, 1), phase('design', null, 1)],
}

const points = [
  { week_start: '2026-10-05', avg_cycle_days: 17, n_buds: 1 },
  { week_start: '2026-10-12', avg_cycle_days: 15, n_buds: 2 },
]

describe('medianCycle and shippedTotal', () => {
  it('handles empty and even-length series', () => {
    expect(medianCycle([])).toBeNull()
    expect(medianCycle(points)).toBe(16)
    expect(shippedTotal(points)).toBe(3)
  })
})

describe('stageRow', () => {
  it('orders stages by lifecycle and drops empty ones', () => {
    const row = stageRow(simple)
    expect(row.parts.map(p => p.phase)).toEqual(['bud', 'development', 'testing'])
    expect(row.parts[1]).toMatchObject({ label: 'Development', color: 'stage-development', days: 2 })
    expect(row.totalDays).toBe(3.5)
  })
})

describe('stageLegend', () => {
  it('lists every stage once in lifecycle order', () => {
    const legend = stageLegend([stageRow(simple), stageRow(complex)])
    expect(legend.map(p => p.phase)).toEqual(['bud', 'development', 'code_review', 'testing'])
  })
})

describe('slowestStage', () => {
  it('weights each complexity by its samples', () => {
    const slowest = slowestStage([simple, complex])
    expect(slowest?.label).toBe('Development')
    expect(slowest?.days).toBeCloseTo(11 / 3)
    expect(slowestStage([complex])).toEqual({ label: 'Development', days: 7 })
    expect(slowestStage([])).toBeNull()
  })
})

describe('mondayOf', () => {
  it('finds the Monday on or before a date', () => {
    expect(mondayOf(new Date('2026-10-28T12:00:00Z'))).toBe('2026-10-26')
    expect(mondayOf(new Date('2026-10-26T00:00:00Z'))).toBe('2026-10-26')
    expect(mondayOf(new Date('2026-11-01T23:00:00Z'))).toBe('2026-10-26')
  })
})

describe('weeklyShipped', () => {
  it('fills the weeks without closures', () => {
    const weeks = weeklyShipped(points, new Date('2026-10-28T12:00:00Z'), 4)
    expect(weeks.map(w => w.weekStart)).toEqual(['2026-10-05', '2026-10-12', '2026-10-19', '2026-10-26'])
    expect(weeks.map(w => w.shipped)).toEqual([1, 2, 0, 0])
    expect(weeks[0]).toMatchObject({ label: 'Oct 5', avgCycleDays: 17 })
    expect(weeks[3].avgCycleDays).toBeNull()
  })
  it('covers the whole backend window by default', () => {
    expect(weeklyShipped([], new Date('2026-10-28T12:00:00Z'))).toHaveLength(13)
  })
})

describe('learningsKpis', () => {
  it('reads the overview into four tiles', () => {
    const kpis = learningsKpis(points, [simple], [{ phase: 'testing', median_drift_pct: 40, buds_over_estimate: 2, buds_total: 3 }])
    expect(kpis.map(k => k.value)).toEqual(['3', '16.0d', 'Development', '1'])
  })
  it('says when there is not enough data', () => {
    const kpis = learningsKpis([], [], [])
    expect(kpis[1].value).toBe(formatDays(null))
    expect(kpis[2].sub).toBe('Needs more closed BUDs')
  })
})
