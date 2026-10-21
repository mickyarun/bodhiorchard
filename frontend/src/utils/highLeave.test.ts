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

import type { HighLeave } from '@/types/leave'
import { highLeaveForOthers, highLeaveForSelf, highLeaveShort, highLeaveVariant } from '@/utils/highLeave'

const notice: HighLeave = { level: 'notice', taken: '16', notice_days: 15, warning_days: 18 }
const warning: HighLeave = { level: 'warning', taken: '19.5', notice_days: 15, warning_days: 18 }

describe('high-leave wording', () => {
  it('gives the person a heads-up, then the firmer warning', () => {
    expect(highLeaveForSelf(notice, false)).toBe("Heads-up: you've taken 16 days of leave this year (heads-up at 15).")
    expect(highLeaveForSelf(notice, true)).toBe(
      "Heads-up: with this request, you'll have taken 16 days of leave this year (heads-up at 15).",
    )
    expect(highLeaveForSelf(warning, true)).toBe(
      "You've taken too many leaves already. With this request, you'll have taken 19.5 days this year, past the 18-day line.",
    )
  })

  it('names the person for approvers and HR', () => {
    expect(highLeaveForOthers(notice, 'Ravi')).toBe('Ravi has taken 16 days of leave this year (heads-up at 15).')
    expect(highLeaveForOthers(warning, 'Ravi')).toBe(
      'Ravi has taken too many leaves: 19.5 days this year, past the 18-day line.',
    )
  })

  it('maps levels to callout variants and a short label', () => {
    expect([highLeaveVariant(notice), highLeaveVariant(warning)]).toEqual(['info', 'warning'])
    expect(highLeaveShort(warning)).toBe('19.5 days this year')
  })
})
