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

/** Leave dates and requests for the People specs. */
import { Api } from './api.ts'
import type { Member } from './stack.ts'

export interface LeaveDays {
  /** `YYYY-MM-DD`, as the date inputs take it. */
  from: string
  to: string
  start: Date
}

const iso = (day: Date): string =>
  `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`

/**
 * Monday and Tuesday a few weeks out. Near the year end it moves to the
 * second week of January, so a request never spans two leave years.
 */
export function upcomingWeekdays(weeksAhead = 3): LeaveDays {
  const today = new Date()
  const monday = new Date(today.getFullYear(), today.getMonth(), today.getDate())
  monday.setDate(monday.getDate() + ((8 - monday.getDay()) % 7 || 7) + 7 * weeksAhead)
  if (monday.getMonth() === 11 && monday.getDate() > 20) {
    monday.setFullYear(monday.getFullYear() + 1, 0, 8)
    monday.setDate(monday.getDate() + ((8 - monday.getDay()) % 7))
  }
  const tuesday = new Date(monday)
  tuesday.setDate(monday.getDate() + 1)
  return { from: iso(monday), to: iso(tuesday), start: monday }
}

interface LeaveRequest {
  id: string
  status: string
}

/** Files a leave request through the API, as the employee. */
export async function requestLeave(member: Member, leaveTypeId: string, days: LeaveDays, reason: string): Promise<LeaveRequest> {
  const api = await Api.as(member)
  try {
    return await api.post<LeaveRequest>('leave/requests', {
      kind: 'leave', leave_type_id: leaveTypeId, start_date: days.from, end_date: days.to, reason,
    })
  } finally {
    await api.dispose()
  }
}

export async function approveLeave(approver: Member, requestId: string): Promise<void> {
  const api = await Api.as(approver)
  try {
    await api.post(`leave/requests/${requestId}/approve`, {})
  } finally {
    await api.dispose()
  }
}
