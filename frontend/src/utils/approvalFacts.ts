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
import { pluralDays, toNumber, toNumberOrNull } from '@/utils/leave'
import { formatDayRange, parseIsoDate } from '@/utils/leaveDates'

const DAY_MS = 86_400_000

/** "today", "yesterday", "5 days ago", "3 weeks ago", "4 months ago". */
export function timeAgo(iso: string, today: Date): string {
  const midnight = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  const days = Math.round((midnight.getTime() - parseIsoDate(iso).getTime()) / DAY_MS)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 14) return `${days} days ago`
  if (days < 63) return `${Math.floor(days / 7)} weeks ago`
  const months = Math.floor(days / 30.44)
  return months < 24 ? `${months} months ago` : `${Math.floor(months / 12)} years ago`
}

/** "Sick leave · Wed 2 – Thu 3 Sep · 2 days · 7 weeks ago"; "on leave now" if it hasn't ended. */
export function lastLeaveLine(last: LastLeave, today: Date): string {
  const ended = parseIsoDate(last.end_date) < new Date(today.getFullYear(), today.getMonth(), today.getDate())
  return [
    last.leave_type ?? 'Leave',
    formatDayRange(last.start_date, last.end_date),
    pluralDays(toNumber(last.days)),
    ended ? timeAgo(last.end_date, today) : 'on leave now',
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
