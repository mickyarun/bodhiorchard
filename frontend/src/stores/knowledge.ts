// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'
import type { KnowledgeItem, KnowledgeItemPage } from '@/types'

export const PAGE_SIZE = 24

interface FetchArgs {
  page?: number
  repoId?: string
  q?: string
}

export const useKnowledgeStore = defineStore('knowledge', () => {
  const items = ref<KnowledgeItem[]>([])
  const total = ref(0)
  const selectedItem = ref<KnowledgeItem | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchItems({ page = 1, repoId, q }: FetchArgs = {}): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const params: Record<string, string | number> = {
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      }
      if (repoId) params.repoId = repoId
      if (q) params.q = q
      const { data } = await api.get<KnowledgeItemPage>('/v1/skills/knowledge', { params })
      items.value = data.items
      total.value = data.total
    } catch {
      error.value = 'Failed to load knowledge items.'
      items.value = []
      total.value = 0
    } finally {
      loading.value = false
    }
  }

  async function fetchItem(id: string): Promise<void> {
    error.value = null
    try {
      const { data } = await api.get(`/v1/skills/knowledge/${id}`)
      selectedItem.value = data
    } catch {
      error.value = 'Failed to load knowledge item.'
    }
  }

  return {
    items,
    total,
    selectedItem,
    loading,
    error,
    fetchItems,
    fetchItem,
  }
})
