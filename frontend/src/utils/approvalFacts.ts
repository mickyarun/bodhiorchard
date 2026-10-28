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

/** Plain-text facts on an approval card: the last leave, and the balance
 *  after approval when the request falls in another leave year. */
import type { ApprovalItem, LastLeave } from '@/types/leave'
import { type RelativeTimeOptions, relativeTime } from '@/utils/date'
import { pluralDays, toNumber, toNumberOrNull } from '@/utils/leave'
import { formatDayRange, parseIsoDate } from '@/utils/leaveDates'

/** Leave ages count whole local days: "today", "yesterday", "3 weeks ago". */
const DAYS_AGO: RelativeTimeOptions = { granularity: 'day', older: 'span' }

/** "Sick leave · Wed 2 – Thu 3 Sep · 2 days · 7 weeks ago"; "on leave now" if it hasn't ended. */
export function lastLeaveLine(last: LastLeave, today: Date): string {
  const ended = parseIsoDate(last.end_date) < new Date(today.getFullYear(), today.getMonth(), today.getDate())
  return [
    last.leave_type ?? 'Leave',
    formatDayRange(last.start_date, last.end_date),
    pluralDays(toNumber(last.days)),
    ended ? relativeTime(parseIsoDate(last.end_date), today, DAYS_AGO) : 'on leave now',
  ].join(' · ')
}

/** Whether the request falls in the leave year the balance tiles show. */
export function inBalanceYear(item: ApprovalItem): boolean {
  return item.balance_after_year === null || item.balance_after_year === item.balance_year
}

/**
 * Days left after approval when the request is in another leave year than
 * the tiles (the requester's current one), so no tile shows it.
 */
export function otherYearBalanceAfter(item: ApprovalItem): number | null {
  return inBalanceYear(item) ? null : toNumberOrNull(item.balance_after)
}

/** How long ago an API timestamp was, counted in local days: "2 days ago". */
export function timestampAgo(timestamp: string, today: Date): string {
  return relativeTime(timestamp, today, DAYS_AGO)
}

/**
 * "6 requests waiting on you · oldest sent 2 days ago", or with filters on,
 * "2 matching requests · oldest sent …". Empty when there are none.
 */
export function queueSummary(items: ApprovalItem[], today: Date, filtered: boolean): string {
  if (!items.length) return ''
  const noun = items.length === 1 ? 'request' : 'requests'
  const count = filtered ? `${items.length} matching ${noun}` : `${items.length} ${noun} waiting on you`
  const oldest = items.reduce((min, i) =>
    Date.parse(i.request.created_at) < Date.parse(min) ? i.request.created_at : min, items[0].request.created_at)
  return `${count} · oldest sent ${timestampAgo(oldest, today)}`
}
