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

import { filenameFrom } from '@/utils/download'
import { presetRange } from '@/utils/leaveRanges'

// Wednesday 20 May 2026, local time.
const TODAY = new Date(2026, 4, 20)

describe('presetRange', () => {
  it.each([
    ['this_week', '2026-05-18', '2026-05-24'],
    ['this_month', '2026-05-01', '2026-05-31'],
    ['last_month', '2026-04-01', '2026-04-30'],
    ['next_30_days', '2026-05-20', '2026-06-18'],
    ['this_quarter', '2026-04-01', '2026-06-30'],
    ['this_year', '2026-01-01', '2026-12-31'],
  ] as const)('%s', (preset, start, end) => {
    expect(presetRange(preset, TODAY)).toEqual({ start, end })
  })

  it('rolls last month back over a year end', () => {
    expect(presetRange('last_month', new Date(2026, 0, 10))).toEqual({
      start: '2025-12-01',
      end: '2025-12-31',
    })
  })

  it('keeps the current range for custom', () => {
    const current = { start: '2026-02-03', end: '2026-02-09' }
    expect(presetRange('custom', TODAY, current)).toBe(current)
  })
})

describe('filenameFrom', () => {
  it('reads plain and encoded names', () => {
    expect(filenameFrom('attachment; filename="leave-summary-2026-06.csv"', 'x.csv')).toBe(
      'leave-summary-2026-06.csv',
    )
    expect(filenameFrom("attachment; filename*=UTF-8''a%20b.csv", 'x.csv')).toBe('a b.csv')
  })

  it('falls back when the header is missing', () => {
    expect(filenameFrom(undefined, 'leave-history.csv')).toBe('leave-history.csv')
  })
})
