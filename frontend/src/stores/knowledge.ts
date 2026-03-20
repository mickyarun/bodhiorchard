import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'
import type { KnowledgeItem, KnowledgeSearchResult } from '@/types'

export const useKnowledgeStore = defineStore('knowledge', () => {
  const items = ref<KnowledgeItem[]>([])
  const searchResults = ref<KnowledgeSearchResult[]>([])
  const selectedItem = ref<KnowledgeItem | null>(null)
  const loading = ref(false)
  const searching = ref(false)
  const error = ref<string | null>(null)

  async function fetchItems(category?: string, repoId?: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const params: Record<string, string | number> = { limit: 200 }
      if (category) params.category = category
      if (repoId) params.repoId = repoId
      const { data } = await api.get('/v1/skills/knowledge', { params })
      items.value = data
      searchResults.value = []
    } catch {
      error.value = 'Failed to load knowledge items.'
    } finally {
      loading.value = false
    }
  }

  async function searchItems(query: string, category?: string): Promise<void> {
    if (!query.trim()) {
      searchResults.value = []
      return
    }
    searching.value = true
    error.value = null
    try {
      const body: Record<string, string | number> = { query, limit: 50 }
      if (category) body.category = category
      const { data } = await api.post('/v1/skills/knowledge/search', body)
      searchResults.value = data
    } catch {
      error.value = 'Search failed. Check AI configuration.'
    } finally {
      searching.value = false
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
    searchResults,
    selectedItem,
    loading,
    searching,
    error,
    fetchItems,
    searchItems,
    fetchItem,
  }
})
