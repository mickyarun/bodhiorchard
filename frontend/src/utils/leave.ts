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

/** Labels, numbers and copy for leave. Date math lives in leaveDates.ts. */
import type {
  ApprovalRoute,
  Balance,
  Decimalish,
  ExcludedDate,
  HalfDay,
  LeaveKind,
  LeaveProblem,
  LeaveStatus,
  LeaveTypeBrief,
  PersonRef,
  SwatchKey,
  WfhApproval,
} from '@/types/leave'
import { WEEKDAY_SHORT, weekdayIndex } from '@/utils/leaveDates'

export const KIND_LABELS: Record<LeaveKind, string> = {
  leave: 'Leave',
  wfh: 'Work from home',
  optional_holiday: 'Optional holiday',
}

/** Shorter kind labels for tight spaces, e.g. the request type toggle on a phone. */
export const KIND_SHORT_LABELS: Record<LeaveKind, string> = {
  leave: 'Leave',
  wfh: 'WFH',
  optional_holiday: 'Optional holiday',
}

export const HALF_DAY_LABELS: Record<HalfDay, string> = {
  none: 'Full day',
  first_half: 'Morning',
  second_half: 'Afternoon',
}

export const WFH_APPROVAL_LABELS: Record<WfhApproval, string> = {
  required: 'Always needs approval',
  auto: 'Approved automatically',
  auto_within_allowance: 'Approved automatically up to N days a month',
}

export const ROUTE_TAGS: Record<ApprovalRoute, string> = {
  manager: 'Your team',
  hr_queue: 'HR queue',
  hr_override: 'HR',
}

export const STATUS_META: Record<LeaveStatus, { label: string; color: string; icon: string }> = {
  pending: { label: 'Pending', color: 'warning', icon: 'mdi-clock-outline' },
  approved: { label: 'Approved', color: 'success', icon: 'mdi-check' },
  rejected: { label: 'Rejected', color: 'error', icon: 'mdi-close' },
  cancelled: { label: 'Cancelled', color: 'muted', icon: 'mdi-cancel' },
}

/** `{ label, value }` options for an AppPillToggle from a label map. */
export function pillOptions<T extends string>(labels: Record<T, string>): { label: string; value: T }[] {
  return (Object.keys(labels) as T[]).map(value => ({ label: labels[value], value }))
}

/** Leave-type colour keys are theme colours of the same name (tokens.css
 *  --color-swatch-*), a categorical palette kept apart from status colours. */
export const SWATCH_KEYS = [
  'swatch-1',
  'swatch-2',
  'swatch-3',
  'swatch-4',
  'swatch-5',
  'swatch-6',
  'swatch-7',
] as const satisfies readonly SwatchKey[]

function isSwatchKey(key: string): key is SwatchKey {
  return (SWATCH_KEYS as readonly string[]).includes(key)
}

/** Theme colour name for a leave type's colour key; unknown keys get the first swatch. */
export function swatchColor(key: string | null | undefined): SwatchKey {
  return key && isSwatchKey(key) ? key : SWATCH_KEYS[0]
}

/** Decimal from the API (string or number) as a number; blanks are 0. */
export function toNumber(value: Decimalish | null | undefined): number {
  if (value === null || value === undefined || value === '') return 0
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

/** Like toNumber, but null stays null ("no limit"). */
export function toNumberOrNull(value: Decimalish | null | undefined): number | null {
  return value === null || value === undefined ? null : toNumber(value)
}

/** 3 → "3", 2.5 → "2.5", 1.25 → "1.3". */
export function formatDays(value: number): string {
  return String(Number(value.toFixed(1)))
}

/** "1 day", "2.5 days". */
export function pluralDays(value: number): string {
  return `${formatDays(value)} ${value === 1 ? 'day' : 'days'}`
}

/** How long a request is: "3 days", or "Half day, morning". */
export function requestLength(request: { days: Decimalish; half_day: HalfDay }): string {
  if (request.half_day === 'none') return pluralDays(toNumber(request.days))
  return `Half day, ${HALF_DAY_LABELS[request.half_day].toLowerCase()}`
}

/** "2 days loss of pay", or '' when there are none. */
export function lopLabel(value: Decimalish | null | undefined): string {
  const days = toNumber(value)
  return days > 0 ? `${pluralDays(days)} loss of pay` : ''
}

/** "+2", "−1.5" (a real minus sign). */
export function formatSignedDays(value: number): string {
  if (value < 0) return `−${formatDays(-value)}`
  return `+${formatDays(value)}`
}

/** Allowance for the year (allocation plus adjustments), or null. */
export function balanceTotal(balance: Balance): number | null {
  if (balance.allocated === null) return null
  return toNumber(balance.allocated) + toNumber(balance.adjustments)
}

/**
 * Meter fill in percent: used, then pending, never over 100 together. The
 * track is what is earned so far and its free part is what can still be
 * booked ("days left"), so the bar always agrees with the number, even when
 * a monthly type has leave booked for later months.
 */
export function meterPercents(balance: Balance): { used: number; pending: number } | null {
  if (balance.allocated === null) return null
  const total = toNumber(balance.earned ?? balance.allocated) + toNumber(balance.adjustments)
  if (total <= 0) return { used: 0, pending: 0 }
  const free = Math.min(total, Math.max(0, toNumber(balance.available)))
  const filled = total - free
  const used = Math.min(toNumber(balance.used), filled)
  const pending = Math.min(toNumber(balance.pending), filled - used)
  return { used: (used / total) * 100, pending: (pending / total) * 100 }
}

/** "3 used · 1 pending · of 12" (pending only when there is some). */
export function balanceCaption(balance: Balance): string {
  const parts = [`${formatDays(toNumber(balance.used))} used`]
  const pending = toNumber(balance.pending)
  if (pending > 0) parts.push(`${formatDays(pending)} pending`)
  const total = balanceTotal(balance)
  if (total !== null) parts.push(`of ${formatDays(total)}`)
  return parts.join(' · ')
}

/** "Casual leave", "Work from home", "Optional holiday · Diwali". */
export function requestTypeLabel(request: {
  kind: LeaveKind
  leave_type: LeaveTypeBrief | null
  holiday_name?: string | null
}): string {
  if (request.kind === 'leave') return request.leave_type?.name ?? KIND_LABELS.leave
  if (request.kind === 'optional_holiday' && request.holiday_name) {
    return `${KIND_LABELS.optional_holiday} · ${request.holiday_name}`
  }
  return KIND_LABELS[request.kind]
}

/** "A", "A and B", "A, B and C". */
export function joinWithAnd(items: string[]): string {
  if (items.length <= 1) return items[0] ?? ''
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

export function firstName(name: string): string {
  return name.trim().split(/\s+/)[0] ?? name
}

/** "skips Sat, Sun and Diwali": weekdays off by name, otherwise the
 *  server's reason (a holiday name). Empty when nothing is skipped. */
export function excludedSummary(excluded: ExcludedDate[], workingDays: number[]): string {
  const labels: string[] = []
  for (const item of excluded) {
    const weekday = weekdayIndex(item.date)
    const label = workingDays.includes(weekday) ? item.reason : WEEKDAY_SHORT[weekday]
    if (!labels.includes(label)) labels.push(label)
  }
  return labels.length ? `skips ${joinWithAnd(labels)}` : ''
}

/** Who decides, in a sentence, for the request preview. Empty when nobody
 *  can: the preview's `no_approver` problem already says so. */
export function approvalLine(
  preview: {
    auto_approved: boolean
    routes_to_hr: boolean
    approvers: PersonRef[]
    problems: LeaveProblem[]
  },
  kind: LeaveKind,
  wfhApproval: WfhApproval | null,
): string {
  if (preview.problems.some(p => p.code === 'no_approver')) return ''
  if (preview.auto_approved) {
    return kind === 'wfh' && wfhApproval === 'auto_within_allowance'
      ? "Approved automatically (within this month's WFH allowance)"
      : 'Approved automatically'
  }
  if (preview.routes_to_hr || preview.approvers.length === 0) return 'Goes to HR for approval'
  return `Goes to ${joinWithAnd(preview.approvers.map(p => p.name))} for approval`
}

/** Short code from a type name: "Casual leave" → "CL", "Sick" → "SIC". */
export function codeFromName(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean)
  if (words.length === 0) return ''
  const code = words.length > 1 ? words.map(w => w[0]).join('') : words[0].slice(0, 3)
  return code.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 10)
}
