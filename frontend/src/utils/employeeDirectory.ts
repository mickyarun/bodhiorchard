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
 * Pure helpers for the employee directory: the department and office
 * filters (applied to the rows the API already returned for the search and
 * status) and the one-line summary under the page title.
 */
import type { DirectoryEntry, OfficeRef, WorkArrangement } from '@/types/employee'
import { ARRANGEMENT_LABELS } from '@/utils/employee'

/** Department chip label for people with no department set. */
export const NO_DEPARTMENT = 'No department'
/** Office filter value for remote people, who have no office. */
export const REMOTE_FILTER = 'remote'

export interface DepartmentCount {
  name: string
  count: number
}

export interface DirectoryFilter {
  /** A department name, NO_DEPARTMENT, or null for everyone. */
  department: string | null
  /** An office id, REMOTE_FILTER, or null for everywhere. */
  office: string | null
}

function departmentOf(row: DirectoryEntry): string {
  return row.department?.trim() || NO_DEPARTMENT
}

/** Departments with how many people each, biggest first, then by name. */
export function departmentCounts(rows: DirectoryEntry[]): DepartmentCount[] {
  const counts = new Map<string, number>()
  for (const row of rows) {
    const name = departmentOf(row)
    counts.set(name, (counts.get(name) ?? 0) + 1)
  }
  return [...counts]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name))
}

/** Office filter choices: every office someone sits in, then Remote. */
export function officeOptions(rows: DirectoryEntry[]): { title: string; value: string }[] {
  const offices = new Map<string, string>()
  for (const row of rows) if (row.office) offices.set(row.office.id, row.office.name)
  const options = [...offices]
    .map(([value, title]) => ({ title, value }))
    .sort((a, b) => a.title.localeCompare(b.title))
  if (rows.some(row => row.work_arrangement === 'remote')) {
    options.push({ title: 'Remote', value: REMOTE_FILTER })
  }
  return options
}

export function filterDirectory(rows: DirectoryEntry[], filter: DirectoryFilter): DirectoryEntry[] {
  return rows.filter(row => {
    if (filter.department && departmentOf(row) !== filter.department) return false
    if (filter.office === REMOTE_FILTER) return row.work_arrangement === 'remote'
    if (filter.office) return row.office?.id === filter.office
    return true
  })
}

/** "Chennai", "Chennai and London", "Chennai, London and Pune". */
function joinNames(names: string[]): string {
  if (names.length <= 1) return names.join('')
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

/** "11 people · Chennai and London offices · 2 remote". */
export function directorySummary(rows: DirectoryEntry[]): string {
  const people = `${rows.length} ${rows.length === 1 ? 'person' : 'people'}`
  const offices = [...new Set(rows.flatMap(row => (row.office ? [row.office.name] : [])))].sort(
    (a, b) => a.localeCompare(b),
  )
  const remote = rows.filter(row => row.work_arrangement === 'remote').length
  const parts = [people]
  if (offices.length) {
    parts.push(`${joinNames(offices)} ${offices.length === 1 ? 'office' : 'offices'}`)
  }
  if (remote) parts.push(`${remote} remote`)
  return parts.join(' · ')
}

/** People whose primary manager is `managerId`, other than `selfId`. */
export function reportsOf(
  rows: DirectoryEntry[],
  managerId: string,
  selfId: string,
): DirectoryEntry[] {
  return rows.filter(row => row.primary_manager?.user_id === managerId && row.user_id !== selfId)
}

/** "Office · Chennai", "Hybrid · London", "Remote": how first, then where. */
export function worksFromLabel(arrangement: WorkArrangement, office: OfficeRef | null): string {
  const how = ARRANGEMENT_LABELS[arrangement]
  return arrangement !== 'remote' && office ? `${how} · ${office.name}` : how
}
