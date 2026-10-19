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
 * Date-only helpers for leave: ranges, leave years and the month grid.
 *
 * Every 'YYYY-MM-DD' string is read as a LOCAL date. `new Date(iso)` is
 * UTC midnight and lands on the previous day west of Greenwich.
 * Weekday indexes follow the API: 0 = Monday … 6 = Sunday.
 */
import type { LeaveYear } from '@/types/leave'

export const WEEKDAY_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const
export const MONTH_SHORT = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
] as const
export const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
] as const

const MONTH_PARAM = /^(\d{4})-(\d{2})$/

/** A calendar month; `month` is 1–12. */
export interface MonthRef {
  year: number
  month: number
}

export interface GridDay {
  iso: string
  day: number
  inMonth: boolean
  weekday: number
}

export function parseIsoDate(iso: string): Date {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(year, month - 1, day)
}

export function toIsoDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

export function addDays(iso: string, days: number): string {
  const date = parseIsoDate(iso)
  date.setDate(date.getDate() + days)
  return toIsoDate(date)
}

/** 0 = Monday … 6 = Sunday. */
export function weekdayIndex(iso: string): number {
  return (parseIsoDate(iso).getDay() + 6) % 7
}

/** ISO strings compare correctly as text. */
export function isWithin(iso: string, start: string, end: string): boolean {
  return iso >= start && iso <= end
}

function dayLabel(iso: string, withMonth: boolean, withYear: boolean): string {
  const date = parseIsoDate(iso)
  let label = `${WEEKDAY_SHORT[weekdayIndex(iso)]} ${date.getDate()}`
  if (withMonth) label += ` ${MONTH_SHORT[date.getMonth()]}`
  if (withYear) label += ` ${date.getFullYear()}`
  return label
}

/** "Mon 20 Oct", "Mon 20 – Wed 22 Oct", "Wed 30 Sep – Fri 2 Oct". */
export function formatDayRange(start: string, end: string): string {
  if (start === end) return dayLabel(start, true, false)
  const sameYear = start.slice(0, 4) === end.slice(0, 4)
  const sameMonth = sameYear && start.slice(0, 7) === end.slice(0, 7)
  const from = dayLabel(start, !sameMonth, !sameYear)
  return `${from} – ${dayLabel(end, true, !sameYear)}`
}

function shortDate(iso: string, withYear: boolean): string {
  const date = parseIsoDate(iso)
  const label = `${date.getDate()} ${MONTH_SHORT[date.getMonth()]}`
  return withYear ? `${label} ${date.getFullYear()}` : label
}

/** "1 Jan – 31 Dec 2026", or "1 Apr 2026 – 31 Mar 2027". */
export function formatLeaveYear(year: LeaveYear): string {
  const sameYear = year.start.slice(0, 4) === year.end.slice(0, 4)
  return `${shortDate(year.start, !sameYear)} – ${shortDate(year.end, true)}`
}

export function monthOf(date: Date): MonthRef {
  return { year: date.getFullYear(), month: date.getMonth() + 1 }
}

export function formatMonthParam(month: MonthRef): string {
  return `${month.year}-${String(month.month).padStart(2, '0')}`
}

/** Read `?month=YYYY-MM`; anything else falls back. */
export function parseMonthParam(value: unknown, fallback: MonthRef): MonthRef {
  if (typeof value !== 'string') return fallback
  const match = value.match(MONTH_PARAM)
  if (!match) return fallback
  const month = Number(match[2])
  if (month < 1 || month > 12) return fallback
  return { year: Number(match[1]), month }
}

export function shiftMonth(month: MonthRef, delta: number): MonthRef {
  const index = month.year * 12 + (month.month - 1) + delta
  return { year: Math.floor(index / 12), month: (((index % 12) + 12) % 12) + 1 }
}

export function monthTitle(month: MonthRef): string {
  return `${MONTH_NAMES[month.month - 1]} ${month.year}`
}

/** Every date in the month, in order. */
export function monthDays(month: MonthRef): string[] {
  const count = new Date(month.year, month.month, 0).getDate()
  return Array.from({ length: count }, (_, i) =>
    toIsoDate(new Date(month.year, month.month - 1, i + 1)),
  )
}

/** Whole weeks (Monday first) covering the month, padded with the
 *  neighbouring months' days. */
export function buildMonthGrid(month: MonthRef): GridDay[][] {
  const days = monthDays(month)
  const monthKey = formatMonthParam(month)
  let cursor = addDays(days[0], -weekdayIndex(days[0]))
  const last = addDays(days[days.length - 1], 6 - weekdayIndex(days[days.length - 1]))
  const weeks: GridDay[][] = []
  while (cursor <= last) {
    const week: GridDay[] = []
    for (let weekday = 0; weekday < 7; weekday += 1) {
      week.push({
        iso: cursor,
        day: parseIsoDate(cursor).getDate(),
        inMonth: cursor.slice(0, 7) === monthKey,
        weekday,
      })
      cursor = addDays(cursor, 1)
    }
    weeks.push(week)
  }
  return weeks
}
