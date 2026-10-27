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

/** Pure helpers for the Bugs list: filters, labels and the BUD filter. */
import { budRef, type BugListItem, type BugSeverity, type BugStatusValue, type BugType } from '@/types'
import type { FilterOption } from '@/utils/budBoard'

export type BugScope = BugType | 'all'
/** Status filter: still open (open, in progress, blocked), resolved, closed, or rejected as a false positive. */
export type BugStatusGroup = 'open' | 'resolved' | 'closed' | 'rejected'

export const BUG_SCOPE_OPTIONS: Array<{ label: string; value: BugScope }> = [
  { label: 'Production', value: 'production' },
  { label: 'Testing', value: 'testing' },
  { label: 'All', value: 'all' },
]

export const BUG_SEVERITY_OPTIONS: FilterOption<BugSeverity>[] = [
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
]

export const BUG_STATUS_GROUP_OPTIONS: FilterOption<BugStatusGroup>[] = [
  { value: 'open', label: 'Open' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'closed', label: 'Closed' },
  { value: 'rejected', label: 'Rejected' },
]

export const BUG_TYPE_LABELS: Record<BugType, string> = { production: 'Production', testing: 'Testing' }

const STILL_OPEN: ReadonlySet<string> = new Set<BugStatusValue>(['open', 'in-progress', 'blocked'])

export function isScope(value: unknown): value is BugScope {
  return value === 'production' || value === 'testing' || value === 'all'
}

/** "BUG-007". */
export function bugRef(n: number): string {
  return `BUG-${String(n).padStart(3, '0')}`
}

export function severityLabel(severity: BugSeverity): string {
  return BUG_SEVERITY_OPTIONS.find(o => o.value === severity)?.label ?? severity
}

export function statusGroupOf(status: string): BugStatusGroup {
  if (STILL_OPEN.has(status)) return 'open'
  if (status === 'resolved' || status === 'rejected') return status
  return 'closed'
}

/**
 * Status tags stay neutral so severity carries the colour in a row; only
 * a blocked bug, which needs someone to act, is tinted.
 */
export function statusTagColor(status: string): string | undefined {
  return status === 'blocked' ? 'warning' : undefined
}

/** Moves that need a confirm: they stamp the resolve time or settle QA SP and can't be taken back cleanly. */
const CONFIRM_STATUS: Partial<Record<BugStatusValue, { title: string; body: string; action: string }>> = {
  resolved: {
    title: 'Mark as resolved?',
    body: 'A resolved bug is awaiting QA validation; the assignee should be notified.',
    action: 'Mark resolved',
  },
  closed: {
    title: 'Close this bug?',
    body: 'Closed bugs leave the open list. Closing a production bug reported by QA awards the reporter SP, which stays awarded if the bug is reopened.',
    action: 'Close bug',
  },
  rejected: {
    title: 'Reject this bug?',
    body: 'Rejecting marks the report as a false positive. A QA reporter loses SP for it.',
    action: 'Reject bug',
  },
}

export function statusConfirm(status: BugStatusValue): { title: string; body: string; action: string } | null {
  return CONFIRM_STATUS[status] ?? null
}

/** The board endpoint returns at most this many bugs (``BugRepository.list_board``). */
export const BOARD_LIMIT = 500
/** The BUD-filtered list endpoint's page-size ceiling. */
export const BUD_LIST_LIMIT = 100

/** "Showing the newest 100 of 140 bugs." when a list was cut short; null otherwise. */
export function truncationNote(shown: number, total: number | null, limit: number): string | null {
  if (total !== null && total > shown) return `Showing the newest ${shown} of ${total} bugs.`
  if (total === null && shown >= limit) return `Showing the newest ${limit} bugs; older ones aren't listed.`
  return null
}

export function openCount(bugs: Pick<BugListItem, 'status'>[]): number {
  return bugs.filter(b => STILL_OPEN.has(b.status)).length
}

/** Every bug on the board, newest first, whatever column it sits in. */
export function flattenBoard(columns: Record<string, BugListItem[] | undefined>): BugListItem[] {
  return Object.values(columns)
    .flatMap(list => list ?? [])
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
}

export interface BugFilters {
  scope: BugScope
  severity: BugSeverity | null
  status: BugStatusGroup | null
}

/** Client-side filters; the board endpoint already applied scope and severity, the BUD list didn't. */
export function filterBugs(bugs: BugListItem[], f: BugFilters): BugListItem[] {
  return bugs.filter(
    b =>
      (f.scope === 'all' || b.bugType === f.scope) &&
      (f.severity === null || b.severity === f.severity) &&
      (f.status === null || statusGroupOf(b.status) === f.status),
  )
}

/** "web-app · Billing export": the module and feature a bug was filed against. */
export function bugWhere(bug: Pick<BugListItem, 'module' | 'featureTitle'>): string {
  return [bug.module, bug.featureTitle].filter(Boolean).join(' · ')
}

/**
 * "BUD-014 · Board load time" for the BUD filter, from the BUD list when
 * it's loaded, else the number on one of its bugs.
 */
export function budFilterLabel(
  budId: string,
  buds: Array<{ id: string; bud_number: number; title: string }>,
  bugs: Pick<BugListItem, 'budId' | 'budNumber'>[],
): string {
  const bud = buds.find(b => b.id === budId)
  if (bud) return `${budRef(bud.bud_number)} · ${bud.title}`
  const n = bugs.find(b => b.budId === budId && b.budNumber !== null)?.budNumber
  return n != null ? budRef(n) : 'one BUD'
}
