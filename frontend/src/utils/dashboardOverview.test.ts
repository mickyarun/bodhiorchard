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
import { BUD_STATUS_ORDER, type BUDListItem } from '@/types'
import { attentionItems, flowStages, greetingFor, overviewKpis } from './dashboardOverview'

let seq = 0
function bud(over: Partial<BUDListItem>): BUDListItem {
  seq += 1
  return {
    id: `b${seq}`, bud_number: seq, title: `BUD ${seq}`, status: 'bud', priority: 'P2',
    complexity: null, prod_p70_date: null, current_phase_deadline: null,
    assignee_id: null, assignee_name: null, open_bug_count: 0,
    created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z',
    ...over,
  }
}

describe('flowStages', () => {
  it('counts open BUDs per stage through prod and drops closed and discarded', () => {
    const stages = flowStages(
      [bud({ status: 'design' }), bud({ status: 'design' }), bud({ status: 'closed' })],
      BUD_STATUS_ORDER,
    )
    expect(stages.map(s => s.status)).toEqual(
      ['bud', 'design', 'tech_arch', 'development', 'code_review', 'testing', 'uat', 'prod'])
    expect(stages.find(s => s.status === 'design')?.count).toBe(2)
    expect(stages.find(s => s.status === 'code_review')?.label).toBe('Review')
  })

  it('follows the org phase order, so a disabled UAT stage disappears', () => {
    const order = BUD_STATUS_ORDER.filter(s => s !== 'uat')
    expect(flowStages([], order).some(s => s.status === 'uat')).toBe(false)
  })
})

describe('overviewKpis', () => {
  const buds = [
    bud({ status: 'bud' }), bud({ status: 'development', open_bug_count: 2 }),
    bud({ status: 'code_review' }), bud({ status: 'uat' }), bud({ status: 'prod' }),
    bud({ status: 'closed', open_bug_count: 5 }),
  ]

  it('shows the leave queue to approvers', () => {
    const kpis = overviewKpis(buds, 6, true)
    expect(kpis.map(k => k.value)).toEqual([4, 1, 2, 6])
    expect(kpis[3].to).toBe('/leave/approvals')
  })

  it('shows open bugs on work in flight to everyone else', () => {
    const last = overviewKpis(buds, null, true)[3]
    expect(last).toMatchObject({ label: 'Open bugs', value: 2, to: '/bugs' })
  })

  it('leaves UAT out of the review count when the org has no UAT stage', () => {
    expect(overviewKpis(buds, null, false)[2]).toMatchObject({ value: 1, sub: 'Code review' })
  })
})

describe('attentionItems', () => {
  it('lists review, UAT and in-flight P0 work, highest priority first', () => {
    const items = attentionItems([
      bud({ status: 'code_review', priority: 'P2', title: 'review me' }),
      bud({ status: 'development', priority: 'P0', title: 'urgent', assignee_name: 'Meera Iyer' }),
      bud({ status: 'prod', priority: 'P0', title: 'already live' }),
      bud({ status: 'development', priority: 'P1', title: 'just working' }),
    ], 5)
    expect(items.map(i => i.title)).toEqual(['urgent', 'review me'])
    expect(items[0]).toMatchObject({ action: 'Open', meta: 'Development · Meera Iyer · highest priority' })
    expect(items[1].action).toBe('Review')
  })

  it('caps the list', () => {
    const many = Array.from({ length: 8 }, () => bud({ status: 'uat' }))
    expect(attentionItems(many, 5)).toHaveLength(5)
  })
})

describe('greetingFor', () => {
  it('follows the time of day', () => {
    expect([greetingFor(8), greetingFor(13), greetingFor(20)])
      .toEqual(['Good morning', 'Good afternoon', 'Good evening'])
  })
})
