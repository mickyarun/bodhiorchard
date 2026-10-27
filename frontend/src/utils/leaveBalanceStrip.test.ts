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

import type { Balance } from '@/types/leave'
import { balanceChipLabel, wfhAllowanceLine } from '@/utils/leaveBalanceStrip'

function balance(used: number, pending: number): Balance {
  return {
    leave_type: { id: 't1', name: 'Casual', code: 'CL', color_key: 'swatch-1' },
    is_paid: true,
    accrual: 'upfront',
    allocated: 12,
    earned: 12,
    adjustments: 0,
    added: 0,
    used,
    pending,
    available: 12 - used - pending,
  }
}

describe('balance strip', () => {
  it('shows used, and pending only when there is some', () => {
    expect(balanceChipLabel(balance(2, 0))).toBe('Casual: 2 used')
    expect(balanceChipLabel(balance(2.5, 1))).toBe('Casual: 2.5 used · 1 pending')
  })

  it('describes the WFH allowance', () => {
    expect(wfhAllowanceLine(null)).toBe('')
    expect(wfhAllowanceLine(1)).toBe('1 day of work from home left this month without approval.')
    expect(wfhAllowanceLine(0)).toBe('Work from home this month now needs approval.')
  })
})
