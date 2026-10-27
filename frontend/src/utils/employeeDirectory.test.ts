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

import { describe, expect, it } from 'vitest'
import type { DirectoryEntry, WorkArrangement } from '@/types/employee'
import {
  departmentCounts,
  directorySummary,
  filterDirectory,
  NO_DEPARTMENT,
  officeOptions,
  REMOTE_FILTER,
  reportsOf,
  worksFromLabel,
} from './employeeDirectory'

const CHENNAI = { id: 'o-chennai', name: 'Chennai' }
const LONDON = { id: 'o-london', name: 'London' }

function row(
  id: string,
  department: string | null,
  arrangement: WorkArrangement,
  office: { id: string; name: string } | null,
  managerId: string | null = null,
): DirectoryEntry {
  return {
    user_id: id,
    avatar_url: null,
    name: id,
    email: `${id}@example.com`,
    is_active: true,
    employee_code: null,
    designation: null,
    department,
    status: 'active',
    work_arrangement: arrangement,
    office,
    primary_manager: managerId
      ? { user_id: managerId, name: managerId, is_primary: true, is_active: true }
      : null,
    manager_count: managerId ? 1 : 0,
  }
}

const ROWS = [
  row('a', 'Engineering', 'office', CHENNAI, 'm'),
  row('b', 'Engineering', 'remote', null, 'm'),
  row('c', 'Sales', 'hybrid', LONDON),
  row('d', null, 'office', CHENNAI, 'm'),
]

describe('departmentCounts', () => {
  it('counts each department, biggest first, with a bucket for none', () => {
    expect(departmentCounts(ROWS)).toEqual([
      { name: 'Engineering', count: 2 },
      { name: NO_DEPARTMENT, count: 1 },
      { name: 'Sales', count: 1 },
    ])
  })
})

describe('officeOptions', () => {
  it('lists offices by name, then Remote when anyone is remote', () => {
    expect(officeOptions(ROWS)).toEqual([
      { title: 'Chennai', value: 'o-chennai' },
      { title: 'London', value: 'o-london' },
      { title: 'Remote', value: REMOTE_FILTER },
    ])
  })

  it('leaves Remote out when nobody is', () => {
    expect(officeOptions([ROWS[2]])).toEqual([{ title: 'London', value: 'o-london' }])
  })
})

describe('filterDirectory', () => {
  it('returns everyone with no filter', () => {
    expect(filterDirectory(ROWS, { department: null, office: null })).toHaveLength(4)
  })

  it('filters by department, including people with none', () => {
    const ids = (department: string) =>
      filterDirectory(ROWS, { department, office: null }).map(r => r.user_id)
    expect(ids('Engineering')).toEqual(['a', 'b'])
    expect(ids(NO_DEPARTMENT)).toEqual(['d'])
  })

  it('filters by office or remote, combined with department', () => {
    expect(
      filterDirectory(ROWS, { department: null, office: 'o-chennai' }).map(r => r.user_id),
    ).toEqual(['a', 'd'])
    expect(
      filterDirectory(ROWS, { department: 'Engineering', office: REMOTE_FILTER }).map(
        r => r.user_id,
      ),
    ).toEqual(['b'])
  })
})

describe('directorySummary', () => {
  it('names the offices and counts remote people', () => {
    expect(directorySummary(ROWS)).toBe('4 people · Chennai and London offices · 1 remote')
  })

  it('reads well for one person and one office', () => {
    expect(directorySummary([ROWS[0]])).toBe('1 person · Chennai office')
  })

  it('lists three offices with commas', () => {
    const pune = row('e', null, 'office', { id: 'o-pune', name: 'Pune' })
    expect(directorySummary([ROWS[0], ROWS[2], pune])).toBe(
      '3 people · Chennai, London and Pune offices',
    )
  })

  it('says nothing about offices for an empty list', () => {
    expect(directorySummary([])).toBe('0 people')
  })
})

describe('reportsOf', () => {
  it('finds the other people who report to the same primary manager', () => {
    expect(reportsOf(ROWS, 'm', 'a').map(r => r.user_id)).toEqual(['b', 'd'])
  })
})

describe('worksFromLabel', () => {
  it('puts the arrangement first, then the office', () => {
    expect(worksFromLabel('office', CHENNAI)).toBe('Office · Chennai')
    expect(worksFromLabel('hybrid', LONDON)).toBe('Hybrid · London')
    expect(worksFromLabel('hybrid', null)).toBe('Hybrid')
    expect(worksFromLabel('remote', null)).toBe('Remote')
  })
})
