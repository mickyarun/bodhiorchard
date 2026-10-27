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
import {
  formatDateOnly,
  formatTimestampDay,
  normalizeManagers,
  setPrimary,
  workplaceLabel,
} from './employee'

describe('formatDateOnly', () => {
  it('formats a date-only string without shifting the day', () => {
    expect(formatDateOnly('2026-10-20')).toBe('20 Oct 2026')
  })

  it('shows a dash for missing dates', () => {
    expect(formatDateOnly(null)).toBe('—')
  })
})

describe('normalizeManagers', () => {
  it('makes the first manager primary when none is marked', () => {
    expect(normalizeManagers([{ user_id: 'a', is_primary: false }, { user_id: 'b', is_primary: false }]))
      .toEqual([{ user_id: 'a', is_primary: true }, { user_id: 'b', is_primary: false }])
  })

  it('keeps a marked primary and drops duplicates', () => {
    expect(
      normalizeManagers([
        { user_id: 'a', is_primary: false },
        { user_id: 'b', is_primary: true },
        { user_id: 'a', is_primary: false },
      ]),
    ).toEqual([{ user_id: 'a', is_primary: false }, { user_id: 'b', is_primary: true }])
  })

  it('returns an empty list unchanged', () => {
    expect(normalizeManagers([])).toEqual([])
  })
})

describe('setPrimary', () => {
  it('moves the primary flag', () => {
    expect(setPrimary([{ user_id: 'a', is_primary: true }, { user_id: 'b', is_primary: false }], 'b'))
      .toEqual([{ user_id: 'a', is_primary: false }, { user_id: 'b', is_primary: true }])
  })
})

describe('workplaceLabel', () => {
  const london = { id: 'o1', name: 'London' }

  it('says remote whatever the office', () => {
    expect(workplaceLabel('remote', london)).toBe('Remote')
  })

  it('puts the arrangement first, then the office', () => {
    expect(workplaceLabel('office', london)).toBe('Office · London')
    expect(workplaceLabel('hybrid', london)).toBe('Hybrid · London')
  })

  it('gives just the arrangement when no office is set', () => {
    expect(workplaceLabel('office', null)).toBe('Office')
    expect(workplaceLabel('hybrid', null)).toBe('Hybrid')
  })
})

describe('formatTimestampDay', () => {
  it("uses the viewer's day, not the UTC one", () => {
    // Late evening local time on 20 Oct is the same instant as some UTC
    // time; whatever the zone, the local calendar day is what shows.
    const local = new Date(2026, 9, 20, 23, 30)
    expect(formatTimestampDay(local.toISOString())).toBe('20 Oct 2026')
  })
})
