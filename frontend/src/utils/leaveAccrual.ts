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

/** Wording for leave types whose allowance is earned month by month. */
import type { Balance } from '@/types/leave'
import { formatDays, toNumber, toNumberOrNull } from '@/utils/leave'

/** "Earned 15 of 18 so far" while a monthly type is still building up; '' otherwise. */
export function earnedSoFar(balance: Pick<Balance, 'accrual' | 'allocated' | 'earned'>): string {
  if (balance.accrual !== 'monthly') return ''
  const allocated = toNumberOrNull(balance.allocated)
  const earned = toNumberOrNull(balance.earned)
  if (allocated === null || earned === null || earned >= allocated) return ''
  return `Earned ${formatDays(earned)} of ${formatDays(allocated)} so far`
}

/**
 * A balance card's caption while a monthly type is still building up:
 * "Earned 10 of 12 so far · 2 used · 1 pending". Null otherwise, so the
 * usual "2 used · of 12" caption applies.
 */
export function earningCaption(balance: Balance): string | null {
  const earned = earnedSoFar(balance)
  if (!earned) return null
  const parts = [earned, `${formatDays(toNumber(balance.used))} used`]
  const pending = toNumber(balance.pending)
  if (pending > 0) parts.push(`${formatDays(pending)} pending`)
  return parts.join(' · ')
}
