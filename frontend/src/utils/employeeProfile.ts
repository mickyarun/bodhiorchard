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

/**
 * Pure helpers for the employee profile: how long someone has been here,
 * their next work anniversary and birthday, and the short leave summary
 * beside the profile.
 */
import type { EmployeeWork } from '@/types/employee'
import type { Balance } from '@/types/leave'
import { balanceTotal, formatDays, meterPercents, swatchColor, toNumber } from '@/utils/leave'
import { plural } from '@/utils/format'
import { earnedSoFar } from '@/utils/leaveAccrual'

/** "2022-01-10" as a local date (no time-zone shift), or null. */
export function parseDateOnly(iso: string | null | undefined): Date | null {
  if (!iso) return null
  const [year, month, day] = iso.split('-').map(Number)
  if (!year || !month || !day) return null
  return new Date(year, month - 1, day)
}

function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}

/** Whole months from `from` to `to`, counting a month only once its day is reached. */
function monthsBetween(from: Date, to: Date): number {
  const months = (to.getFullYear() - from.getFullYear()) * 12 + to.getMonth() - from.getMonth()
  return to.getDate() < from.getDate() ? months - 1 : months
}

/** "4 years 9 months", "3 months", "Less than a month"; null before they start. */
export function tenureLabel(joining: string | null, today: Date): string | null {
  const start = parseDateOnly(joining)
  if (!start || start > startOfDay(today)) return null
  const months = monthsBetween(start, today)
  if (months < 1) return 'Less than a month'
  const years = Math.floor(months / 12)
  const rest = months % 12
  return [years ? plural(years, 'year') : '', rest ? plural(rest, 'month') : '']
    .filter(Boolean)
    .join(' ')
}

/**
 * Tenure for the profile header. It stops at the exit date for someone who
 * has left, and isn't shown at all when that date is missing.
 */
export function tenureFor(
  work: Pick<EmployeeWork, 'date_of_joining' | 'date_of_exit' | 'status'>,
  today: Date,
): string | null {
  if (work.status !== 'exited') return tenureLabel(work.date_of_joining, today)
  const exit = parseDateOnly(work.date_of_exit)
  if (!exit) return null
  return tenureLabel(work.date_of_joining, exit < today ? exit : today)
}

/** The day-and-month of `source` in `year`; 29 Feb falls back to 28 Feb. */
function sameDayIn(source: Date, year: number): Date {
  const date = new Date(year, source.getMonth(), source.getDate())
  return date.getMonth() === source.getMonth() ? date : new Date(year, source.getMonth() + 1, 0)
}

/** The next time `source`'s day and month come round, today included. */
function nextOccurrence(source: Date, today: Date): Date {
  const day = startOfDay(today)
  const thisYear = sameDayIn(source, day.getFullYear())
  return thisYear >= day ? thisYear : sameDayIn(source, day.getFullYear() + 1)
}

export interface Anniversary {
  date: Date
  years: number
}

/** The next work anniversary (one year or more), or null without a joining date. */
export function nextAnniversary(joining: string | null, today: Date): Anniversary | null {
  const start = parseDateOnly(joining)
  if (!start) return null
  let date = nextOccurrence(start, today)
  if (date.getFullYear() <= start.getFullYear()) date = sameDayIn(start, start.getFullYear() + 1)
  return { date, years: date.getFullYear() - start.getFullYear() }
}

/** The next birthday, or null when the date of birth isn't known. */
export function nextBirthday(dateOfBirth: string | null, today: Date): Date | null {
  const born = parseDateOnly(dateOfBirth)
  return born ? nextOccurrence(born, today) : null
}

/** "10 Jan 2027". */
export function formatFullDate(date: Date): string {
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

/** "14 Mar": birthdays never show the year. */
export function formatDayMonth(date: Date): string {
  return date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

export interface LeaveSummaryRow {
  key: string
  name: string
  /**
   * "9 of 12 left"; "8 left · 10 earned of 12" while a monthly type is still
   * building up; "0 left" with nothing allocated; "3 days taken" with no limit.
   */
  left: string
  /** Share of the earned days still free, or null for a type with no limit. */
  percent: number | null
  /** Theme colour name for the bar. */
  color: string
}

/**
 * One row per leave type for the profile's "Leave this year" panel, worded
 * like the Leave tab's balance cards so the two never disagree.
 */
export function leaveSummary(balances: Balance[]): LeaveSummaryRow[] {
  return balances.map(balance => {
    const base = {
      key: balance.leave_type.id,
      name: balance.leave_type.name,
      color: swatchColor(balance.leave_type.color_key),
    }
    const meter = meterPercents(balance)
    const total = balanceTotal(balance)
    if (!meter || total === null) {
      const used = toNumber(balance.used)
      return { ...base, left: `${formatDays(used)} ${used === 1 ? 'day' : 'days'} taken`, percent: null }
    }
    const available = formatDays(Math.max(0, toNumber(balance.available)))
    if (total <= 0) return { ...base, left: `${available} left`, percent: 0 }
    // The bar's track is what is earned so far, as on the Leave tab.
    const percent = Math.max(0, 100 - meter.used - meter.pending)
    if (earnedSoFar(balance)) {
      const earned = formatDays(toNumber(balance.earned))
      const allocated = formatDays(toNumber(balance.allocated))
      return { ...base, left: `${available} left · ${earned} earned of ${allocated}`, percent }
    }
    return { ...base, left: `${available} of ${formatDays(total)} left`, percent }
  })
}

export type ProfileTab = 'personal' | 'employment' | 'leave' | 'bank' | 'documents'

export interface ProfileTabItem {
  value: ProfileTab
  label: string
  /** Encrypted, revealed one value at a time: shown with a lock. */
  locked: boolean
}

/** The profile tabs this viewer gets, in order; Employment is always there. */
export function profileTabs(show: {
  personal: boolean
  leave: boolean
  details: boolean
  documents: boolean
}): ProfileTabItem[] {
  const tabs: (ProfileTabItem & { visible: boolean })[] = [
    { value: 'personal', label: 'Personal', locked: false, visible: show.personal },
    { value: 'employment', label: 'Employment', locked: false, visible: true },
    { value: 'leave', label: 'Leave', locked: false, visible: show.leave },
    { value: 'bank', label: 'Bank and IDs', locked: true, visible: show.details },
    { value: 'documents', label: 'Documents', locked: false, visible: show.documents },
  ]
  return tabs.filter(tab => tab.visible).map(({ visible: _visible, ...tab }) => tab)
}
