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

import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'
import { createBugComments } from '@/stores/bugComments'
import { extractApiError } from '@/utils/errors'
import {
  type BugBoardFilters,
  type BugListFilters,
  bugBoardParams,
  bugListParams,
  emptyBoard,
} from '@/stores/bugQuery'
import {
  BUG_BOARD_COLUMNS,
  type BugBoardResponse,
  type BugListItem,
  type BugListResponse,
  type BugRead,
  type BugStatusValue,
} from '@/types'

export const useBugsStore = defineStore('bugs', () => {
  const bugs = ref<BugListItem[]>([])
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(20)
  const loading = ref(false)
  const boardLoading = ref(false)
  const error = ref<string | null>(null)
  const currentBug = ref<BugRead | null>(null)
  const board = ref<Record<BugStatusValue, BugListItem[]>>(emptyBoard())
  // Load failures for the list and board, kept apart from ``error`` (a
  // failed save, comment or attachment) so a page can show them in place.
  const loadError = ref<string | null>(null)
  const { comments, commentsLoading, fetchComments, addComment, editComment, deleteComment } =
    createBugComments(error, _bumpCommentCount)

  async function fetchBugs(filters?: BugListFilters): Promise<void> {
    loading.value = true
    loadError.value = null
    try {
      const params = bugListParams(filters, page.value, pageSize.value)
      const { data } = await api.get<BugListResponse>('/v1/bugs', { params })
      bugs.value = data.items
      total.value = data.total
      page.value = data.page
      pageSize.value = data.pageSize
    } catch (err) {
      loadError.value = extractApiError(err, 'Failed to load bugs.')
    } finally {
      loading.value = false
    }
  }

  async function fetchBoard(filters?: BugBoardFilters): Promise<void> {
    boardLoading.value = true
    loadError.value = null
    try {
      const params = bugBoardParams(filters)
      const { data } = await api.get<BugBoardResponse>('/v1/bugs/board', { params })
      const merged = emptyBoard()
      for (const col of BUG_BOARD_COLUMNS) {
        merged[col] = data.columns[col] ?? []
      }
      board.value = merged
    } catch (err) {
      loadError.value = extractApiError(err, 'Failed to load bugs.')
    } finally {
      boardLoading.value = false
    }
  }

  async function fetchBug(bugId: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get<BugRead>(`/v1/bugs/${bugId}`)
      currentBug.value = data
    } catch (err) {
      error.value = extractApiError(err, 'Failed to load bug.')
    } finally {
      loading.value = false
    }
  }

  async function createBug(body: {
    title: string
    description?: string
    severity?: string
    module?: string
    budId?: string
    featureId?: string
    bugType?: 'testing' | 'production'
  }): Promise<BugRead | null> {
    error.value = null
    try {
      const { data } = await api.post<BugRead>('/v1/bugs', body)
      return data
    } catch (err) {
      error.value = extractApiError(err, 'Failed to create bug.')
      return null
    }
  }

  async function updateBug(
    bugId: string,
    body: Record<string, unknown>,
  ): Promise<BugRead | null> {
    error.value = null
    try {
      const { data } = await api.patch<BugRead>(`/v1/bugs/${bugId}`, body)
      currentBug.value = data
      return data
    } catch (err) {
      error.value = extractApiError(err, 'Failed to update bug.')
      return null
    }
  }

  async function fetchBugsForBud(budId: string): Promise<BugListItem[]> {
    try {
      const { data } = await api.get<BugListResponse>('/v1/bugs', {
        params: { budId, pageSize: 100 },
      })
      return data.items
    } catch {
      return []
    }
  }

  /**
   * Bump the cached comment counts on every reactive view that holds
   * this bug — currentBug, the paginated list, and every board column.
   * Counts are floored at 0 so a stale-state delete never goes negative.
   */
  function _bumpCommentCount(bugId: string, delta: number): void {
    const apply = (n: number) => Math.max(0, n + delta)
    if (currentBug.value && currentBug.value.id === bugId) {
      currentBug.value.commentCount = apply(currentBug.value.commentCount ?? 0)
    }
    const listEntry = bugs.value.find((b) => b.id === bugId)
    if (listEntry) listEntry.commentCount = apply(listEntry.commentCount ?? 0)
    for (const col of BUG_BOARD_COLUMNS) {
      const card = board.value[col]?.find((b) => b.id === bugId)
      if (card) card.commentCount = apply(card.commentCount ?? 0)
    }
  }

  return {
    // state
    bugs,
    total,
    page,
    pageSize,
    loading,
    boardLoading,
    error,
    currentBug,
    board,
    loadError,
    comments,
    commentsLoading,
    // bug ops
    fetchBugs,
    fetchBoard,
    fetchBug,
    createBug,
    updateBug,
    fetchBugsForBud,
    // comment ops
    fetchComments,
    addComment,
    editComment,
    deleteComment,
  }
})
