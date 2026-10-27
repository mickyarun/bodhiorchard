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

// Pure helpers behind the BUD board: filtering the kanban columns, the
// assignee dropdown, and the per-card status lines.

import { BUD_PRIORITY_WEIGHTS, type BUDListItem, type BUDPriority } from '@/types'

const DAY_MS = 86_400_000

/** Assignee filter value for BUDs nobody owns. Not a user id, so it can't collide. */
export const UNASSIGNED = '__unassigned__'

export interface BoardFilters {
  query: string
  assignee: string | null
  priority: BUDPriority | null
  /** Members of the picked team; null when no team filter is set. */
  teamMemberIds: ReadonlySet<string> | null
  sortByPriority: boolean
}

export interface FilterOption<V extends string = string> {
  value: V
  label: string
}

/** True when the BUD's title or number matches the search text ("BUD-014", "014", "14"). */
export function matchesQuery(bud: BUDListItem, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  if (bud.title?.toLowerCase().includes(q)) return true
  const numericQ = q.replace(/^bud-?/, '').replace(/^0+/, '')
  return numericQ !== '' && String(bud.bud_number).includes(numericQ)
}

function matchesFilters(bud: BUDListItem, f: BoardFilters): boolean {
  if (f.assignee === UNASSIGNED && bud.assignee_id) return false
  if (f.assignee && f.assignee !== UNASSIGNED && bud.assignee_id !== f.assignee) return false
  if (f.priority && bud.priority !== f.priority) return false
  // A team filter keeps only BUDs whose assignee is in the team; an
  // unowned BUD has no team to belong to.
  if (f.teamMemberIds && (!bud.assignee_id || !f.teamMemberIds.has(bud.assignee_id))) return false
  return matchesQuery(bud, f.query)
}

/** Applies the board filters to each status column, keeping every column. */
export function filterBoard(
  grouped: Record<string, BUDListItem[]>,
  f: BoardFilters,
): Record<string, BUDListItem[]> {
  const out: Record<string, BUDListItem[]> = {}
  for (const [status, buds] of Object.entries(grouped)) {
    const kept = buds.filter(b => matchesFilters(b, f))
    out[status] = f.sortByPriority
      ? kept.sort((a, b) => BUD_PRIORITY_WEIGHTS[a.priority] - BUD_PRIORITY_WEIGHTS[b.priority])
      : kept
  }
  return out
}

/** Assignees present on the board, by name, plus "Unassigned" when some BUD has no owner. */
export function assigneeOptions(buds: BUDListItem[]): FilterOption[] {
  const seen = new Map<string, string>()
  let hasUnassigned = false
  for (const bud of buds) {
    if (bud.assignee_id && bud.assignee_name) seen.set(bud.assignee_id, bud.assignee_name)
    else hasUnassigned = true
  }
  const opts = [...seen.entries()]
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label))
  if (hasUnassigned) opts.push({ value: UNASSIGNED, label: 'Unassigned' })
  return opts
}

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

/** "Today", "1 day", "12 days" since the BUD was opened. */
export function budAge(createdAt: string, now: Date): string {
  const days = Math.round((startOfDay(now) - startOfDay(new Date(createdAt))) / DAY_MS)
  if (days <= 0) return 'Today'
  return days === 1 ? '1 day' : `${days} days`
}

export type StatusTone = 'error' | 'warning' | 'success' | 'muted'

export interface CardStatusLine {
  text: string
  tone: StatusTone
}

/** Overdue stage deadlines read as errors, ones under two days away as warnings. */
export function deadlineTone(deadline: string, now: Date): StatusTone {
  const days = (new Date(deadline).getTime() - now.getTime()) / DAY_MS
  if (days < 0) return 'error'
  if (days < 2) return 'warning'
  return 'muted'
}

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

/**
 * The status lines a board card shows, from the data the list endpoint
 * carries: the current stage's deadline, then when it closed, was
 * discarded, or is forecast to go live.
 */
export function cardStatusLines(bud: BUDListItem, now: Date): CardStatusLine[] {
  const lines: CardStatusLine[] = []
  if (bud.current_phase_deadline) {
    lines.push({
      text: `Stage due ${shortDate(bud.current_phase_deadline)}`,
      tone: deadlineTone(bud.current_phase_deadline, now),
    })
  }
  if (bud.status === 'closed') {
    lines.push({ text: `Released ${shortDate(bud.updated_at)}`, tone: 'success' })
  } else if (bud.status === 'discarded') {
    lines.push({ text: `Discarded ${shortDate(bud.updated_at)}`, tone: 'error' })
  } else if (bud.prod_p70_date) {
    lines.push({ text: `Live by ${shortDate(bud.prod_p70_date)} · 70% likely`, tone: 'muted' })
  }
  return lines
}
