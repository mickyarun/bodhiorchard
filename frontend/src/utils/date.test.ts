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
import { formatShortDate, relativeTime } from './date'

describe('formatShortDate', () => {
  it('gives month and day', () => expect(formatShortDate('2026-10-27T12:00:00')).toBe('Oct 27'))
  it('is empty for no date and passes unparseable input through', () => {
    expect(formatShortDate(null)).toBe('')
    expect(formatShortDate('soon')).toBe('soon')
  })
})

describe('relativeTime', () => {
  const now = new Date(2026, 9, 28, 15, 0)
  const at = (d: number, h: number, m = 0): string => new Date(2026, 9, d, h, m).toISOString()

  it('counts minutes and hours within today', () => {
    expect(relativeTime(at(28, 14, 59), now)).toBe('1 minute ago')
    expect(relativeTime(at(28, 14, 30), now)).toBe('30 minutes ago')
    expect(relativeTime(at(28, 13, 0), now)).toBe('2 hours ago')
    expect(relativeTime(at(28, 15, 0), now)).toBe('just now')
  })
  it('counts calendar days before today', () => {
    expect(relativeTime(at(27, 23, 0), now)).toBe('yesterday')
    expect(relativeTime(at(25, 9, 0), now)).toBe('3 days ago')
  })
  it('falls back to the date after a week', () => {
    expect(relativeTime(at(10, 9, 0), now)).toBe('Oct 10')
  })
  it('is empty for no date', () => expect(relativeTime(null, now)).toBe(''))
})

describe('relativeTime short style', () => {
  const now = new Date(2026, 9, 28, 15, 0)
  const at = (d: number, h: number, m = 0): string => new Date(2026, 9, d, h, m).toISOString()
  const short = { style: 'short' } as const

  it('counts elapsed minutes, hours and days', () => {
    expect(relativeTime(at(28, 14, 59), now, short)).toBe('1m ago')
    expect(relativeTime(at(28, 15, 0), now, short)).toBe('just now')
    expect(relativeTime(at(27, 23, 0), now, short)).toBe('16h ago')
    expect(relativeTime(at(26, 14, 0), now, short)).toBe('2d ago')
  })
  it('falls back to the date after a week, or keeps counting days', () => {
    expect(relativeTime(at(10, 9, 0), now, short)).toBe('Oct 10')
    expect(relativeTime(at(10, 9, 0), now, { style: 'short', older: 'span' })).toBe('18d ago')
  })
})

describe('relativeTime spans and whole days', () => {
  // Wednesday 21 October 2026, mid-morning local time.
  const today = new Date(2026, 9, 21, 10, 30)
  const days = { granularity: 'day', older: 'span' } as const

  it.each([
    [new Date(2026, 9, 21), 'today'],
    [new Date(2026, 9, 20), 'yesterday'],
    [new Date(2026, 9, 16), '5 days ago'],
    [new Date(2026, 8, 2), '7 weeks ago'],
    [new Date(2026, 5, 1), '4 months ago'],
    [new Date(2024, 0, 10), '2 years ago'],
  ])('%s → %s', (date, label) => {
    expect(relativeTime(date, today, days)).toBe(label)
  })
  it('counts the local day of a timestamp', () => {
    expect(relativeTime(new Date(2026, 9, 19, 23, 50).toISOString(), today, days)).toBe('2 days ago')
    expect(relativeTime(new Date(2026, 9, 21, 8, 0).toISOString(), today, days)).toBe('today')
  })
  it('keeps minutes and hours unless whole days are asked for', () => {
    const earlier = new Date(2026, 9, 21, 8, 30).toISOString()
    expect(relativeTime(earlier, today, { older: 'span' })).toBe('2 hours ago')
    expect(relativeTime(new Date(2026, 8, 2), today, { older: 'span' })).toBe('7 weeks ago')
  })
})
