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
import type { BugListItem } from '@/types'
import {
  budFilterLabel,
  bugRef,
  bugWhere,
  filterBugs,
  flattenBoard,
  isScope,
  openCount,
  severityLabel,
  statusConfirm,
  statusGroupOf,
  statusTagColor,
  truncationNote,
} from './bugList'

function bug(over: Partial<BugListItem> = {}): BugListItem {
  return {
    id: 'b1', bugNumber: 7, title: 'Broken', severity: 'high', status: 'open', bugType: 'production', module: null,
    budId: null, budNumber: null, featureId: null, featureTitle: null, reporterName: null, assigneeId: null,
    assigneeName: null, commentCount: 0, createdAt: '2026-10-01T00:00:00Z', updatedAt: '2026-10-01T00:00:00Z', ...over,
  }
}

describe('bugList', () => {
  it('formats refs and labels', () => {
    expect(bugRef(7)).toBe('BUG-007')
    expect(severityLabel('critical')).toBe('Critical')
    expect(isScope('testing')).toBe(true)
    expect(isScope('nope')).toBe(false)
  })

  it('groups statuses into open, resolved and closed', () => {
    expect(['open', 'in-progress', 'blocked'].map(statusGroupOf)).toEqual(['open', 'open', 'open'])
    expect(statusGroupOf('resolved')).toBe('resolved')
    expect(statusGroupOf('closed')).toBe('closed')
    expect(statusGroupOf('rejected')).toBe('rejected')
    expect(openCount([bug(), bug({ status: 'blocked' }), bug({ status: 'closed' })])).toBe(2)
  })

  it('flattens the board newest first', () => {
    const rows = flattenBoard({
      open: [bug({ id: 'a', createdAt: '2026-10-01T00:00:00Z' })],
      closed: [bug({ id: 'b', createdAt: '2026-10-03T00:00:00Z' })],
      blocked: undefined,
    })
    expect(rows.map(r => r.id)).toEqual(['b', 'a'])
  })

  it('filters by scope, severity and status', () => {
    const bugs = [
      bug({ id: 'a' }),
      bug({ id: 'b', bugType: 'testing' }),
      bug({ id: 'c', severity: 'low', status: 'resolved' }),
    ]
    const ids = (f: Parameters<typeof filterBugs>[1]): string[] => filterBugs(bugs, f).map(b => b.id)
    expect(ids({ scope: 'all', severity: null, status: null })).toEqual(['a', 'b', 'c'])
    expect(ids({ scope: 'production', severity: null, status: 'open' })).toEqual(['a'])
    expect(ids({ scope: 'all', severity: 'low', status: null })).toEqual(['c'])
  })

  it('says where a bug was filed', () => {
    expect(bugWhere(bug({ module: 'web-app', featureTitle: 'Board' }))).toBe('web-app · Board')
    expect(bugWhere(bug())).toBe('')
  })

  it('names the BUD filter from the BUD list, then its bugs', () => {
    expect(budFilterLabel('x', [{ id: 'x', bud_number: 14, title: 'Board' }], [])).toBe('BUD-014 · Board')
    expect(budFilterLabel('x', [], [bug({ budId: 'x', budNumber: 3 })])).toBe('BUD-003')
    expect(budFilterLabel('x', [], [])).toBe('one BUD')
  })

  it('tints only blocked status tags', () => {
    expect(statusTagColor('blocked')).toBe('warning')
    expect(statusTagColor('open')).toBeUndefined()
  })

  it('asks before moves that stamp or settle SP', () => {
    expect(statusConfirm('closed')?.action).toBe('Close bug')
    expect(statusConfirm('resolved')?.title).toBe('Mark as resolved?')
    expect(statusConfirm('rejected')).not.toBeNull()
    expect(statusConfirm('in-progress')).toBeNull()
  })

  it('says when a list was cut short', () => {
    expect(truncationNote(100, 140, 100)).toBe('Showing the newest 100 of 140 bugs.')
    expect(truncationNote(40, 40, 100)).toBeNull()
    expect(truncationNote(500, null, 500)).toBe("Showing the newest 500 bugs; older ones aren't listed.")
    expect(truncationNote(20, null, 500)).toBeNull()
  })
})
