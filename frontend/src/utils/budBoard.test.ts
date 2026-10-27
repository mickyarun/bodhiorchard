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
import type { BUDListItem } from '@/types'
import {
  UNASSIGNED,
  assigneeOptions,
  budAge,
  cardStatusLines,
  deadlineTone,
  filterBoard,
  matchesQuery,
  type BoardFilters,
} from './budBoard'

let seq = 0
function bud(over: Partial<BUDListItem>): BUDListItem {
  seq += 1
  return {
    id: `b${seq}`, bud_number: seq, title: `BUD ${seq}`, status: 'bud', priority: 'P2',
    complexity: null, prod_p70_date: null, current_phase_deadline: null,
    assignee_id: null, assignee_name: null, open_bug_count: 0,
    created_at: '2026-10-01T10:00:00', updated_at: '2026-10-01T10:00:00',
    ...over,
  }
}

const NONE: BoardFilters = { query: '', assignee: null, priority: null, teamMemberIds: null, sortByPriority: false }
const NOW = new Date('2026-10-28T12:00:00')

describe('matchesQuery', () => {
  const b = bud({ bud_number: 14, title: 'Passkey sign-in' })
  it('matches the title case-insensitively', () => expect(matchesQuery(b, 'PASSKEY')).toBe(true))
  it.each(['BUD-014', 'bud14', '014', '14'])('matches the number written as %s', q => {
    expect(matchesQuery(b, q)).toBe(true)
  })
  it('rejects text that matches neither', () => expect(matchesQuery(b, 'refund')).toBe(false))
  it('matches everything on an empty query', () => expect(matchesQuery(b, '  ')).toBe(true))
})

describe('filterBoard', () => {
  const a = bud({ assignee_id: 'u1', assignee_name: 'Meera', priority: 'P2' })
  const c = bud({ assignee_id: 'u2', assignee_name: 'Lucas', priority: 'P0' })
  const d = bud({ priority: 'P1' })
  const grouped = { bud: [a, c, d], design: [] }

  it('keeps every column, even empty ones', () => {
    expect(Object.keys(filterBoard(grouped, NONE))).toEqual(['bud', 'design'])
  })
  it('filters by assignee and by the unassigned sentinel', () => {
    expect(filterBoard(grouped, { ...NONE, assignee: 'u1' }).bud).toEqual([a])
    expect(filterBoard(grouped, { ...NONE, assignee: UNASSIGNED }).bud).toEqual([d])
  })
  it('filters by priority', () => {
    expect(filterBoard(grouped, { ...NONE, priority: 'P0' }).bud).toEqual([c])
  })
  it('drops unassigned BUDs and non-members under a team filter', () => {
    expect(filterBoard(grouped, { ...NONE, teamMemberIds: new Set(['u2']) }).bud).toEqual([c])
  })
  it('sorts by priority without touching the source column', () => {
    expect(filterBoard(grouped, { ...NONE, sortByPriority: true }).bud).toEqual([c, d, a])
    expect(grouped.bud).toEqual([a, c, d])
  })
})

describe('assigneeOptions', () => {
  it('lists assignees by name and appends Unassigned when needed', () => {
    const opts = assigneeOptions([
      bud({ assignee_id: 'u2', assignee_name: 'Zoe' }),
      bud({ assignee_id: 'u1', assignee_name: 'Ana' }),
      bud({ assignee_id: 'u1', assignee_name: 'Ana' }),
      bud({}),
    ])
    expect(opts).toEqual([
      { value: 'u1', label: 'Ana' },
      { value: 'u2', label: 'Zoe' },
      { value: UNASSIGNED, label: 'Unassigned' },
    ])
  })
})

describe('budAge', () => {
  it('reads Today, 1 day and N days', () => {
    expect(budAge('2026-10-28T08:00:00', NOW)).toBe('Today')
    expect(budAge('2026-10-27T23:00:00', NOW)).toBe('1 day')
    expect(budAge('2026-10-17T09:00:00', NOW)).toBe('11 days')
  })
})

describe('deadlineTone', () => {
  it('flags overdue, near and comfortable deadlines', () => {
    expect(deadlineTone('2026-10-27T12:00:00', NOW)).toBe('error')
    expect(deadlineTone('2026-10-29T12:00:00', NOW)).toBe('warning')
    expect(deadlineTone('2026-11-05T12:00:00', NOW)).toBe('muted')
  })
})

describe('cardStatusLines', () => {
  it('is empty when the card has nothing to report', () => {
    expect(cardStatusLines(bud({}), NOW)).toEqual([])
  })
  it('shows the stage deadline and the go-live forecast', () => {
    const lines = cardStatusLines(
      bud({ current_phase_deadline: '2026-10-27T12:00:00', prod_p70_date: '2026-11-14T12:00:00' }),
      NOW,
    )
    expect(lines).toEqual([
      { text: 'Stage due Oct 27', tone: 'error' },
      { text: 'Live by Nov 14 · 70% likely', tone: 'muted' },
    ])
  })
  it('reports closed and discarded dates instead of a forecast', () => {
    const closed = bud({ status: 'closed', updated_at: '2026-10-20T12:00:00', prod_p70_date: '2026-11-14T12:00:00' })
    expect(cardStatusLines(closed, NOW)).toEqual([{ text: 'Released Oct 20', tone: 'success' }])
    const gone = bud({ status: 'discarded', updated_at: '2026-10-21T12:00:00' })
    expect(cardStatusLines(gone, NOW)).toEqual([{ text: 'Discarded Oct 21', tone: 'error' }])
  })
})
