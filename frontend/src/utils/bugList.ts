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
/** Status filter: still open (open, in progress, blocked), resolved, or closed. */
export type BugStatusGroup = 'open' | 'resolved' | 'closed'

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
]

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
  return status === 'resolved' ? 'resolved' : 'closed'
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
