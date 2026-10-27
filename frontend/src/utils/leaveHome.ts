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

/** Pure helpers for the My leave page: who else is out soon, the request
 *  date badge and the policy notes in "Good to know". */
import type { CalendarEntry, LeaveSummary } from '@/types/leave'
import { joinWithAnd, pluralDays } from '@/utils/leave'
import { addDays, MONTH_SHORT, parseIsoDate } from '@/utils/leaveDates'

export interface OutRow {
  id: string
  name: string
  start: string
  end: string
  /** "Leave" or "WFH": never the leave type, which coworkers don't see. */
  label: string
  pending: boolean
}

/**
 * Other people out from `today` through the next `days - 1` days, approved
 * or pending, soonest first: the first `limit`, and how many more there are.
 * The caller's own requests are left out: they are in "My requests" already.
 */
export function outSoon(
  entries: CalendarEntry[],
  today: string,
  days: number,
  limit: number,
): { rows: OutRow[]; more: number } {
  const last = addDays(today, days - 1)
  const all = entries
    .filter(e => !e.is_own && (e.status === 'approved' || e.status === 'pending'))
    .filter(e => e.end_date >= today && e.start_date <= last)
    .sort((a, b) => a.start_date.localeCompare(b.start_date) || a.user.name.localeCompare(b.user.name))
  const rows = all.slice(0, limit).map(e => ({
      id: e.request_id,
      name: e.user.name,
      start: e.start_date,
      end: e.end_date,
      label: e.kind === 'wfh' ? 'WFH' : 'Leave',
      pending: e.status === 'pending',
    }))
  return { rows, more: all.length - rows.length }
}

/** { month: 'Dec', day: '21' } for the date badge on a request row. */
export function dateBadge(iso: string): { month: string; day: string } {
  const date = parseIsoDate(iso)
  return { month: MONTH_SHORT[date.getMonth()], day: String(date.getDate()) }
}

/** Who decides the caller's requests: "Daniel Okafor", "A and B", or "HR"
 *  when the policy routes to HR, nobody is set, or the summary isn't loaded. */
export function approversOf(summary: LeaveSummary | null): string {
  if (!summary || summary.routes_to_hr || !summary.approvers.length) return 'HR'
  return joinWithAnd(summary.approvers.map(a => a.name))
}

/** Plain sentences about how the caller's policy handles requests. */
export function policyNotes(summary: LeaveSummary): string[] {
  const notes: string[] = [`Requests that need approval go to ${approversOf(summary)}.`]
  const policy = summary.policy
  if (summary.work_arrangement !== 'remote') {
    if (policy.wfh_approval === 'auto') notes.push('Work from home is approved automatically.')
    if (policy.wfh_approval === 'auto_within_allowance') {
      notes.push(
        `Up to ${pluralDays(policy.wfh_monthly_auto_days)} of work from home a month are approved automatically.`,
      )
    }
  }
  if (policy.backdate_limit_days > 0) {
    notes.push(`Requests can go back up to ${pluralDays(policy.backdate_limit_days)}.`)
  }
  notes.push("If a request needs more days than you have left, you'll see that before you send it.")
  return notes
}
