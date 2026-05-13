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
import { ref, computed } from 'vue'
import type { AxiosError } from 'axios'
import type { BUDListItem, BUDDocument, BUDStatus, BUDDesign, BUDEstimates, DesignJobCreated, ChatJobCreatedResponse, ChatMessageRead, TimelineEvent, PRChecklistItem, CodeReviewRepoStatus } from '@/types'
import { BUD_STATUS_ORDER, CODE_REVIEW_OVERRIDE_REASON_MIN } from '@/types'
import api from '@/services/api'
import { extractApiError } from '@/utils/errors'

// Maps legacy DB status values to new pipeline statuses (pre-migration compat)
const LEGACY_STATUS_MAP: Record<string, BUDStatus> = {
  draft: 'bud',
  planning: 'bud',
  designing: 'design',
  in_progress: 'development',
  in_review: 'testing',
  ready: 'prod',
  released: 'prod',
}

function normalizeStatus(status: string): BUDStatus {
  if (BUD_STATUS_ORDER.includes(status as BUDStatus)) return status as BUDStatus
  return LEGACY_STATUS_MAP[status] ?? 'bud'
}

export const useBUDStore = defineStore('bud', () => {
  const buds = ref<BUDListItem[]>([])
  const currentBUD = ref<BUDDocument | null>(null)
  const loading = ref(false)
  const error = ref('')

  const budsByStatus = computed(() => {
    const grouped: Record<string, BUDListItem[]> = {}
    for (const status of BUD_STATUS_ORDER) {
      grouped[status] = []
    }
    for (const bud of buds.value) {
      const resolved = normalizeStatus(bud.status)
      grouped[resolved].push(bud)
    }
    return grouped
  })

  async function fetchBUDs(statusFilter?: BUDStatus): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      const params: Record<string, string> = {}
      if (statusFilter) params.status = statusFilter
      const { data } = await api.get('/v1/buds/', { params })
      buds.value = data
    } catch {
      error.value = 'Failed to load BUDs'
    } finally {
      loading.value = false
    }
  }

  async function fetchBUD(id: string): Promise<BUDDocument | null> {
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.get(`/v1/buds/${id}`)
      currentBUD.value = data
      return data
    } catch {
      error.value = 'Failed to load BUD'
      return null
    } finally {
      loading.value = false
    }
  }

  async function createBUD(title: string, requirements_md?: string): Promise<BUDDocument | null> {
    error.value = ''
    try {
      const { data } = await api.post('/v1/buds/', { title, requirements_md })
      buds.value.unshift(data)
      return data
    } catch {
      error.value = 'Failed to create BUD'
      return null
    }
  }

  // Signal that design phase was entered (frontend should show repo selection)
  const designAvailable = ref(false)

  async function updateBUD(id: string, updates: Partial<BUDDocument>): Promise<BUDDocument | null> {
    error.value = ''
    designAvailable.value = false
    try {
      const resp = await api.patch(`/v1/buds/${id}`, updates)
      const data = resp.data
      const idx = buds.value.findIndex(p => p.id === id)
      if (idx !== -1) buds.value[idx] = data
      if (currentBUD.value?.id === id) currentBUD.value = data
      // Check if backend signals design phase transition
      if (resp.headers['x-design-available'] === 'true') {
        designAvailable.value = true
      }
      return data
    } catch (err) {
      // Surface the backend's detail message verbatim (e.g. "Cannot advance
      // to uat: 3 manual test cases still pending (TM-001, TM-002, TM-003)")
      // instead of a generic fallback — swallowing the detail hides real
      // transition-guard rules from the user.
      error.value = extractApiError(err, 'Failed to update BUD')
      return null
    }
  }

  async function deleteBUD(id: string): Promise<boolean> {
    error.value = ''
    try {
      await api.delete(`/v1/buds/${id}`)
      buds.value = buds.value.filter(p => p.id !== id)
      if (currentBUD.value?.id === id) currentBUD.value = null
      return true
    } catch {
      error.value = 'Failed to delete BUD'
      return false
    }
  }

  async function chatBUD(
    id: string,
    message: string,
    section: string = 'requirements_md',
    designId?: string,
    sessionId?: string,
    images?: string[],
  ): Promise<ChatJobCreatedResponse | null> {
    error.value = ''
    try {
      const body: Record<string, unknown> = { message, section }
      if (designId) body.design_id = designId
      if (sessionId) body.session_id = sessionId
      if (images?.length) body.images = images
      const { data } = await api.post<ChatJobCreatedResponse>(`/v1/buds/${id}/chat`, body)
      return data
    } catch {
      return null
    }
  }

  function exportBUDUrl(id: string, section: string): string {
    return `/v1/buds/${id}/export/${section}`
  }

  async function importBUD(id: string, section: string, file: File): Promise<boolean> {
    error.value = ''
    try {
      const formData = new FormData()
      formData.append('file', file)
      const { data } = await api.post(`/v1/buds/${id}/import/${section}`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      if (currentBUD.value?.id === id) currentBUD.value = data
      return true
    } catch {
      error.value = 'Failed to import file'
      return false
    }
  }

  // ── Design wireframe methods ──────────────────────────

  async function generateDesigns(budId: string, repoIds: string[]): Promise<DesignJobCreated[]> {
    try {
      const { data } = await api.post(`/v1/buds/${budId}/designs/generate`, { repo_ids: repoIds })
      return data
    } catch {
      error.value = 'Failed to start design generation'
      return []
    }
  }

  async function fetchDesigns(budId: string): Promise<BUDDesign[]> {
    try {
      const { data } = await api.get(`/v1/buds/${budId}/designs`)
      return data
    } catch {
      return []
    }
  }

  async function updateDesignHtml(budId: string, designId: string, html: string): Promise<BUDDesign | null> {
    try {
      const { data } = await api.put(`/v1/buds/${budId}/designs/${designId}`, { design_html: html })
      return data
    } catch {
      error.value = 'Failed to update design'
      return null
    }
  }

  async function updateDesignNotes(budId: string, designId: string, notes: string): Promise<BUDDesign | null> {
    try {
      const { data } = await api.put(`/v1/buds/${budId}/designs/${designId}`, { notes })
      return data
    } catch {
      error.value = 'Failed to update notes'
      return null
    }
  }

  async function fetchChatHistory(
    budId: string,
    section: string,
    designId?: string,
    sessionId?: string,
  ): Promise<ChatMessageRead[]> {
    try {
      const params: Record<string, string> = { section }
      if (designId) params.design_id = designId
      if (sessionId) params.session_id = sessionId
      const { data } = await api.get(`/v1/buds/${budId}/chat-history`, { params })
      return data
    } catch {
      return []
    }
  }

  async function fetchTimeline(budId: string): Promise<TimelineEvent[]> {
    try {
      const { data } = await api.get(`/v1/buds/${budId}/timeline`)
      return data
    } catch {
      return []
    }
  }

  async function fetchPRChecklist(budId: string): Promise<PRChecklistItem[]> {
    try {
      const { data } = await api.get(`/v1/buds/${budId}/pr-checklist`)
      return data
    } catch {
      return []
    }
  }

  async function fetchCodeReviewStatus(budId: string): Promise<CodeReviewRepoStatus[]> {
    try {
      const { data } = await api.get(`/v1/buds/${budId}/code-review/status`)
      return data?.repos ?? []
    } catch {
      return []
    }
  }

  async function overrideCodeReview(
    budId: string,
    reason: string,
  ): Promise<BUDDocument | null> {
    error.value = ''
    try {
      const { data } = await api.post(`/v1/buds/${budId}/code-review/override`, { reason })
      if (currentBUD.value?.id === budId) currentBUD.value = data
      const idx = buds.value.findIndex(p => p.id === budId)
      if (idx !== -1) buds.value[idx] = data
      return data
    } catch (err) {
      const axiosErr = err as AxiosError<{ detail?: string }>
      const detail = axiosErr.response?.data?.detail
      if (axiosErr.response?.status === 409) {
        error.value = detail || 'Cannot override — BUD is not in code_review or an agent task is running'
      } else if (axiosErr.response?.status === 422) {
        error.value = detail || `Reason must be at least ${CODE_REVIEW_OVERRIDE_REASON_MIN} characters`
      } else {
        error.value = 'Failed to override code review'
      }
      return null
    }
  }

  async function regenerateDesign(budId: string, designId: string): Promise<DesignJobCreated | null> {
    try {
      const { data } = await api.post(`/v1/buds/${budId}/designs/${designId}/regenerate`)
      return data
    } catch {
      error.value = 'Failed to regenerate design'
      return null
    }
  }

  async function requestReassignment(budId: string, reason: string): Promise<BUDDocument | null> {
    error.value = ''
    try {
      const { data } = await api.post(`/v1/buds/${budId}/request-reassignment`, { reason })
      if (currentBUD.value?.id === budId) currentBUD.value = data
      const idx = buds.value.findIndex(p => p.id === budId)
      if (idx !== -1) buds.value[idx] = data
      return data
    } catch {
      error.value = 'Failed to request reassignment'
      return null
    }
  }

  async function retryAgentTask(budId: string, taskId: string): Promise<void> {
    try {
      await api.post(`/v1/buds/${budId}/agent-tasks/${taskId}/retry`)
      await fetchBUD(budId)
    } catch {
      error.value = 'Failed to retry agent task'
    }
  }

  async function cancelAgentTask(budId: string, taskId: string): Promise<void> {
    // Task-level cancel handles both the live-worker case (signal, worker
    // cleans up) and the orphan case (no worker left, API flips the row).
    try {
      await api.post(`/v1/buds/${budId}/agent-tasks/${taskId}/cancel`)
      await fetchBUD(budId)
    } catch {
      error.value = 'Failed to cancel agent task'
    }
  }

  async function fetchEstimates(budId: string): Promise<BUDEstimates | null> {
    try {
      const { data } = await api.get(`/v1/buds/${budId}/estimates`)
      return data
    } catch {
      // Estimates are optional — don't show global error
      return null
    }
  }

  async function recalculateEstimates(budId: string): Promise<BUDEstimates | null> {
    try {
      const { data } = await api.post(`/v1/buds/${budId}/estimates/recalculate`)
      return data
    } catch {
      error.value = 'Failed to recalculate estimates'
      return null
    }
  }

  async function overrideEstimate(
    budId: string,
    phase: string,
    estimatedCompletion: string,
    reason: string,
  ): Promise<void> {
    try {
      await api.patch(`/v1/buds/${budId}/estimates/${phase}`, {
        estimated_completion: estimatedCompletion,
        reason,
      })
    } catch {
      error.value = 'Failed to override estimate'
    }
  }

  return {
    buds,
    currentBUD,
    loading,
    error,
    designAvailable,
    budsByStatus,
    fetchBUDs,
    fetchBUD,
    createBUD,
    updateBUD,
    deleteBUD,
    chatBUD,
    exportBUDUrl,
    importBUD,
    generateDesigns,
    fetchDesigns,
    updateDesignHtml,
    updateDesignNotes,
    regenerateDesign,
    fetchChatHistory,
    fetchTimeline,
    fetchPRChecklist,
    fetchCodeReviewStatus,
    overrideCodeReview,
    requestReassignment,
    retryAgentTask,
    cancelAgentTask,
    fetchEstimates,
    recalculateEstimates,
    overrideEstimate,
  }
})
