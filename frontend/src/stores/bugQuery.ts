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

/** Query helpers for the bugs store: empty board shape and request params. */
import { BUG_BOARD_COLUMNS, type BugListItem, type BugStatusValue } from '@/types'

export function emptyBoard(): Record<BugStatusValue, BugListItem[]> {
  return BUG_BOARD_COLUMNS.reduce(
    (acc, col) => {
      acc[col] = []
      return acc
    },
    {} as Record<BugStatusValue, BugListItem[]>,
  )
}

export interface BugListFilters {
  status?: string
  severity?: string
  budId?: string
  featureId?: string
  page?: number
  pageSize?: number
}

export interface BugBoardFilters {
  bugType?: 'testing' | 'production' | 'all'
  severity?: string
  featureId?: string
  assigneeId?: string
}

/** Params for ``GET /v1/bugs``; page and size fall back to the store's current ones. */
export function bugListParams(
  filters: BugListFilters | undefined,
  page: number,
  pageSize: number,
): Record<string, string | number> {
  const params: Record<string, string | number> = {}
  if (filters?.status) params.status = filters.status
  if (filters?.severity) params.severity = filters.severity
  if (filters?.budId) params.budId = filters.budId
  if (filters?.featureId) params.featureId = filters.featureId
  params.page = filters?.page ?? page
  params.pageSize = filters?.pageSize ?? pageSize
  return params
}

/** Params for ``GET /v1/bugs/board``, leaving out unset filters. */
export function bugBoardParams(filters: BugBoardFilters | undefined): Record<string, string> {
  const params: Record<string, string> = {}
  if (filters?.bugType) params.bugType = filters.bugType
  if (filters?.severity) params.severity = filters.severity
  if (filters?.featureId) params.featureId = filters.featureId
  if (filters?.assigneeId) params.assigneeId = filters.assigneeId
  return params
}
