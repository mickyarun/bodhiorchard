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
import type { Balance, Decimalish, LeavePreview } from '@/types/leave'
import { formatDays, pluralDays, toNumber, toNumberOrNull } from '@/utils/leave'

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

/** Said wherever "days left" counts days that will be earned later. */
export const BOOKED_AHEAD_NOTE = "Includes what's earned by the booked leave dates"

/** "Up to 1 day a month; unused days lapse." for a type with a monthly limit; '' otherwise. */
export function monthlyLimitNote(balance: Pick<Balance, 'monthly_limit_days'>): string {
  const perMonth = toNumberOrNull(balance.monthly_limit_days)
  return perMonth === null ? '' : `Up to ${pluralDays(perMonth)} a month; unused days lapse.`
}

/**
 * For a monthly type, "days left" can be more than earned + added − used −
 * pending: leave booked for a later month is covered by what is earned by
 * then, so it takes less from today's balance. Returns a line saying so
 * when that happens, so the numbers on the card add up for the reader;
 * '' otherwise. Days taken away only come off the year's total, so they
 * aren't counted here.
 */
export function bookedAheadNote(
  balance: Pick<Balance, 'accrual' | 'earned' | 'added' | 'used' | 'pending' | 'available'>,
): string {
  if (balance.accrual !== 'monthly') return ''
  const earned = toNumberOrNull(balance.earned)
  const available = toNumberOrNull(balance.available)
  if (earned === null || available === null) return ''
  const plain = earned + toNumber(balance.added) - toNumber(balance.used) - toNumber(balance.pending)
  // Decimal strings: compare to a hundredth so rounding never shows the note.
  return available - plain > 0.005 ? BOOKED_AHEAD_NOTE : ''
}

/**
 * A type's days left for the request being drafted. Once the preview has
 * priced the dates, it's what is left on the start date, the same number
 * the preview's "before" shows; until then, what is left today.
 */
export function daysLeftForDraft(
  balance: Pick<Balance, 'leave_type' | 'available'>,
  preview: Pick<LeavePreview, 'balances_on_start'> | null,
): Decimalish | null {
  const onStart = preview?.balances_on_start ?? {}
  const id = balance.leave_type.id
  return id in onStart ? (onStart[id] ?? null) : balance.available
}
