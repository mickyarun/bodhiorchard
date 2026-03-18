import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { PRDListItem, PRDDocument, PRDStatus } from '@/types'
import { PRD_STATUS_ORDER } from '@/types'
import api from '@/services/api'

export const usePRDStore = defineStore('prd', () => {
  const prds = ref<PRDListItem[]>([])
  const currentPRD = ref<PRDDocument | null>(null)
  const loading = ref(false)
  const error = ref('')

  const prdsByStatus = computed(() => {
    const grouped: Record<string, PRDListItem[]> = {}
    for (const status of PRD_STATUS_ORDER) {
      grouped[status] = []
    }
    for (const prd of prds.value) {
      if (grouped[prd.status]) {
        grouped[prd.status].push(prd)
      }
    }
    return grouped
  })

  async function fetchPRDs(statusFilter?: PRDStatus): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      const params: Record<string, string> = {}
      if (statusFilter) params.status = statusFilter
      const { data } = await api.get('/prds', { params })
      prds.value = data
    } catch {
      error.value = 'Failed to load PRDs'
    } finally {
      loading.value = false
    }
  }

  async function fetchPRD(id: string): Promise<PRDDocument | null> {
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.get(`/prds/${id}`)
      currentPRD.value = data
      return data
    } catch {
      error.value = 'Failed to load PRD'
      return null
    } finally {
      loading.value = false
    }
  }

  async function createPRD(title: string, content_md?: string): Promise<PRDDocument | null> {
    error.value = ''
    try {
      const { data } = await api.post('/prds', { title, content_md })
      prds.value.unshift(data)
      return data
    } catch {
      error.value = 'Failed to create PRD'
      return null
    }
  }

  async function updatePRD(id: string, updates: Partial<PRDDocument>): Promise<PRDDocument | null> {
    error.value = ''
    try {
      const { data } = await api.patch(`/prds/${id}`, updates)
      const idx = prds.value.findIndex(p => p.id === id)
      if (idx !== -1) prds.value[idx] = data
      if (currentPRD.value?.id === id) currentPRD.value = data
      return data
    } catch {
      error.value = 'Failed to update PRD'
      return null
    }
  }

  async function deletePRD(id: string): Promise<boolean> {
    error.value = ''
    try {
      await api.delete(`/prds/${id}`)
      prds.value = prds.value.filter(p => p.id !== id)
      if (currentPRD.value?.id === id) currentPRD.value = null
      return true
    } catch {
      error.value = 'Failed to delete PRD'
      return false
    }
  }

  return {
    prds,
    currentPRD,
    loading,
    error,
    prdsByStatus,
    fetchPRDs,
    fetchPRD,
    createPRD,
    updatePRD,
    deletePRD,
  }
})
