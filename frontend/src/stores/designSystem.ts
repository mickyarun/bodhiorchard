import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'

export interface DesignSystemItem {
  id: string
  org_id: string
  repo_id: string
  repo_name: string | null
  is_default: boolean
  content: string
  source_hash: string | null
  extracted_at: string
  created_at: string | null
  updated_at: string | null
}

export const useDesignSystemStore = defineStore('designSystem', () => {
  const items = ref<DesignSystemItem[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchAll(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get('/v1/design-systems/')
      items.value = data
    } catch {
      error.value = 'Failed to load design systems.'
    } finally {
      loading.value = false
    }
  }

  async function extract(
    repoId: string,
    isDefault: boolean,
  ): Promise<string | null> {
    error.value = null
    try {
      const { data } = await api.post<{ jobId: string }>(
        '/v1/design-systems/extract',
        { repo_id: repoId, is_default: isDefault },
      )
      return data.jobId
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { detail?: string } } }
        error.value = axiosErr.response?.data?.detail || 'Extraction failed.'
      } else {
        error.value = 'Extraction failed.'
      }
      return null
    }
  }

  async function setDefault(id: string): Promise<boolean> {
    error.value = null
    try {
      await api.post('/v1/design-systems/set-default', { id })
      await fetchAll()
      return true
    } catch {
      error.value = 'Failed to set default.'
      return false
    }
  }

  async function remove(id: string): Promise<boolean> {
    error.value = null
    try {
      await api.delete(`/v1/design-systems/${id}`)
      items.value = items.value.filter(i => i.id !== id)
      return true
    } catch {
      error.value = 'Failed to delete design system.'
      return false
    }
  }

  async function updateContent(id: string, content: string): Promise<boolean> {
    error.value = null
    try {
      await api.put(`/v1/design-systems/${id}`, { content })
      await fetchAll()
      return true
    } catch {
      error.value = 'Failed to update content.'
      return false
    }
  }

  return { items, loading, error, fetchAll, extract, setDefault, remove, updateContent }
})
