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

export interface DesignSystemItem {
  id: string
  org_id: string
  repo_id: string
  repo_name: string | null
  is_default: boolean
  content: string
  custom_content: string | null
  is_customised: boolean
  // Server-rendered concatenation of ``content`` + the User Customizations
  // divider + ``custom_content``. The Preview dialog renders this directly,
  // so the divider format is single-sourced in the backend repository.
  merged_content: string
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

  async function updateCustomContent(id: string, customContent: string): Promise<boolean> {
    error.value = null
    try {
      await api.put(`/v1/design-systems/${id}`, { custom_content: customContent })
      await fetchAll()
      return true
    } catch {
      error.value = 'Failed to save customisations.'
      return false
    }
  }

  async function resetCustomisations(id: string): Promise<boolean> {
    error.value = null
    try {
      await api.post(`/v1/design-systems/${id}/reset-customisations`)
      await fetchAll()
      return true
    } catch {
      error.value = 'Failed to reset customisations.'
      return false
    }
  }

  return {
    items,
    loading,
    error,
    fetchAll,
    extract,
    setDefault,
    remove,
    updateCustomContent,
    resetCustomisations,
  }
})
