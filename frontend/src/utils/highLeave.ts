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

/** Wording for the high-leave heads-up and warning (unlimited leave). */
import type { HighLeave } from '@/types/leave'
import { formatDays, toNumber } from '@/utils/leave'

export type HighLeaveVariant = 'info' | 'warning'

/** A heads-up reads as information; the warning as a warning. */
export function highLeaveVariant(high: HighLeave): HighLeaveVariant {
  return high.level === 'warning' ? 'warning' : 'info'
}

function days(high: HighLeave): string {
  const n = toNumber(high.taken)
  return `${formatDays(n)} ${n === 1 ? 'day' : 'days'}`
}

/**
 * For the person themself. `withRequest`: the count includes the request
 * being filled in ("With this request, ...").
 */
export function highLeaveForSelf(high: HighLeave, withRequest: boolean): string {
  const lead = withRequest ? "With this request, you'll have taken" : "You've taken"
  if (high.level === 'warning') {
    return `You've taken too many leaves already. ${lead} ${days(high)} this year, past the ${high.warning_days}-day line.`
  }
  return `Heads-up: ${lead.charAt(0).toLowerCase()}${lead.slice(1)} ${days(high)} of leave this year (heads-up at ${high.notice_days}).`
}

/** For an approver or HR, about someone else (pending requests counted). */
export function highLeaveForOthers(high: HighLeave, name: string): string {
  if (high.level === 'warning') {
    return `${name} has taken too many leaves: ${days(high)} this year, past the ${high.warning_days}-day line.`
  }
  return `${name} has taken ${days(high)} of leave this year (heads-up at ${high.notice_days}).`
}

/** Short label for a report cell, e.g. "19 days this year". */
export function highLeaveShort(high: HighLeave): string {
  return `${days(high)} this year`
}
