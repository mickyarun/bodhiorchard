// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'
import { extractApiError } from '@/utils/errors'
import type { BugListItem, BugListResponse, BugRead } from '@/types'

export const useBugsStore = defineStore('bugs', () => {
  const bugs = ref<BugListItem[]>([])
  const total = ref(0)
  const page = ref(1)
  const pageSize = ref(20)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const currentBug = ref<BugRead | null>(null)

  async function fetchBugs(filters?: {
    status?: string
    severity?: string
    budId?: string
    page?: number
    pageSize?: number
  }): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const params: Record<string, string | number> = {}
      if (filters?.status) params.status = filters.status
      if (filters?.severity) params.severity = filters.severity
      if (filters?.budId) params.budId = filters.budId
      params.page = filters?.page ?? page.value
      params.pageSize = filters?.pageSize ?? pageSize.value

      const { data } = await api.get<BugListResponse>('/v1/bugs', { params })
      bugs.value = data.items
      total.value = data.total
      page.value = data.page
      pageSize.value = data.pageSize
    } catch (err) {
      error.value = extractApiError(err, 'Failed to load bugs.')
    } finally {
      loading.value = false
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
  }): Promise<BugRead | null> {
    error.value = null
    try {
      const { data } = await api.post<BugRead>('/v1/bugs', body)
      await fetchBugs()
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
      await fetchBugs()
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

  return {
    bugs,
    total,
    page,
    pageSize,
    loading,
    error,
    currentBug,
    fetchBugs,
    fetchBug,
    createBug,
    updateBug,
    fetchBugsForBud,
  }
})
