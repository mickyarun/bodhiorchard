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
import type { BUDListItem, BUDDocument, BUDStatus, BUDDesign, BUDEstimates, DesignJobCreated, ChatJobCreatedResponse, ChatInProgressDetail, ChatMessageRead, TimelineEvent, PRChecklistItem, CodeReviewStatusResponse, JobStatusRead } from '@/types'
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

  async function createBUD(
    title: string,
    requirements_md?: string,
    stage_skill_overrides?: Record<string, string>,
  ): Promise<BUDDocument | null> {
    error.value = ''
    try {
      const payload: Record<string, unknown> = { title, requirements_md }
      if (stage_skill_overrides && Object.keys(stage_skill_overrides).length > 0) {
        payload.stage_skill_overrides = stage_skill_overrides
      }
      const { data } = await api.post('/v1/buds/', payload)
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

  /**
   * POST a chat request. Returns the job descriptor on 202, or a
   * ``{ stageGateError }`` envelope on 409 so the caller can surface
   * the stage-mismatch banner without optimistically pushing the
   * user message into the visible chat. Returns ``null`` for any
   * other failure (network, 5xx).
   */
  async function chatBUD(
    id: string,
    message: string,
    section: string = 'requirements_md',
    designId?: string,
    sessionId?: string,
    images?: string[],
  ): Promise<
    | ChatJobCreatedResponse
    | { stageGateError: string }
    | { chatInProgressError: ChatInProgressDetail }
    | { permissionError: string }
    | null
  > {
    error.value = ''
    try {
      const body: Record<string, unknown> = { message, section }
      if (designId) body.design_id = designId
      if (sessionId) body.session_id = sessionId
      if (images?.length) body.images = images
      const { data } = await api.post<ChatJobCreatedResponse>(`/v1/buds/${id}/chat`, body)
      return data
    } catch (e) {
      const err = e as {
        response?: {
          status?: number
          data?: { detail?: string | ChatInProgressDetail }
        }
      }
      const detail = err.response?.data?.detail
      const detailString = typeof detail === 'string' ? detail : undefined
      if (err.response?.status === 403) {
        // ``buds:edit`` RBAC rejection. Surface the server's message
        // verbatim when available so the user sees the specific reason
        // ("missing role X", etc.) rather than a generic failure.
        return {
          permissionError:
            detailString ?? "You don't have permission to chat in this section.",
        }
      }
      if (err.response?.status === 409) {
        // Backend uses two 409 shapes for ``POST /chat``:
        // - chat_in_progress: ``detail`` is an object carrying the live
        //   job pointer so the panel can subscribe via resume.
        // - stage-gate: ``detail`` is a string the UI renders verbatim.
        if (
          detail && typeof detail === 'object' && detail.error === 'chat_in_progress'
        ) {
          return { chatInProgressError: detail }
        }
        return { stageGateError: detailString ?? 'Section is locked for this BUD stage.' }
      }
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
      // Mirror into the store so consumers reading ``bud.designs``
      // (per-design banners, chat-panel repo dropdown) react to
      // status transitions in real time. ``BUDDesignPanel.loadDesigns``
      // already calls this on every job onComplete/onError, so the
      // banners flip without needing a full ``fetchBUD``. Bud-id
      // guard prevents a stale fetch from a previous BUD clobbering
      // the now-current one.
      if (currentBUD.value?.id === budId) {
        currentBUD.value = { ...currentBUD.value, designs: data }
      }
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
    signal?: AbortSignal,
  ): Promise<ChatMessageRead[]> {
    try {
      const params: Record<string, string> = { section }
      if (designId) params.design_id = designId
      if (sessionId) params.session_id = sessionId
      const { data } = await api.get(`/v1/buds/${budId}/chat-history`, { params, signal })
      return data
    } catch {
      return []
    }
  }

  async function fetchActiveChatJob(
    budId: string,
    section: string,
    designId?: string,
  ): Promise<JobStatusRead | null> {
    // Looks up an in-flight ``JOB_BUD_CHAT`` job for this BUD/section/design,
    // so the AI Editor panel can re-subscribe to its progress on re-mount
    // (e.g. when the user navigates away mid-chat and comes back).
    try {
      const params: Record<string, string> = { section }
      if (designId) params.design_id = designId
      const { data } = await api.get(`/v1/buds/${budId}/chat/active-job`, { params })
      return data ?? null
    } catch {
      return null
    }
  }

  async function cancelActiveChat(
    budId: string,
    section: string,
    designId?: string,
  ): Promise<boolean> {
    // Signals the backend to stop the in-flight chat job for this thread.
    // The worker's CancelledError branch publishes the terminal WS frame
    // (which the panel's job-socket already listens to) and the finally
    // hook clears the active-job pointer — so the store doesn't need to
    // touch any reactive state itself. Returns true when the cancel
    // landed, false on 404 (nothing to cancel) or any error so the UI
    // can degrade gracefully.
    try {
      const params: Record<string, string> = { section }
      if (designId) params.design_id = designId
      await api.post(`/v1/buds/${budId}/chat/cancel`, undefined, { params })
      return true
    } catch {
      return false
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

  async function fetchCodeReviewStatus(budId: string): Promise<CodeReviewStatusResponse> {
    try {
      const { data } = await api.get<CodeReviewStatusResponse>(
        `/v1/buds/${budId}/code-review/status`,
      )
      return {
        repos: data?.repos ?? [],
        last_run_status: data?.last_run_status ?? 'never_run',
        last_run_message: data?.last_run_message ?? null,
      }
    } catch {
      // Soft failure: keep the tab usable even if the status endpoint
      // is down. The component should never block on a banner load.
      return { repos: [], last_run_status: 'never_run', last_run_message: null }
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

  async function dismissPhaseFailure(budId: string): Promise<void> {
    // Stamp the BUD's acknowledged-at timestamp so the next GET /buds/{id}
    // returns `last_phase_failure: null`. We optimistically clear the
    // local field so the banner hides without waiting for a refetch.
    try {
      await api.post(`/v1/buds/${budId}/phase-failure/dismiss`)
      if (currentBUD.value?.id === budId) {
        currentBUD.value = { ...currentBUD.value, last_phase_failure: null }
      }
    } catch {
      error.value = 'Failed to dismiss phase failure'
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

  async function cancelDesign(budId: string, designId: string): Promise<void> {
    // Per-design cancel: each design row owns its own job_id, so the
    // backend signals only that one Claude run. Lets the user stop
    // one repo's wireframe without affecting parallel repos in the
    // same BUD. 409 detail (signal failed → Claude still running)
    // flows through extractApiError into the snackbar.
    error.value = ''
    try {
      await api.post(`/v1/buds/${budId}/designs/${designId}/cancel`)
      await fetchBUD(budId)
    } catch (err) {
      error.value = extractApiError(err, 'Failed to cancel design')
    }
  }

  async function cancelAgentTask(budId: string, taskId: string): Promise<void> {
    // Task-level cancel: the API delegates to the agent_task_cancel
    // service which signals the in-flight job (if alive) and flips
    // the bud_agent_tasks + bud_designs rows. When the signal itself
    // fails the API returns 409 with a detail message — surface that
    // so the caller can render the real reason in a snackbar instead
    // of a generic "Failed to cancel".
    error.value = ''
    try {
      await api.post(`/v1/buds/${budId}/agent-tasks/${taskId}/cancel`)
      await fetchBUD(budId)
    } catch (err) {
      error.value = extractApiError(err, 'Failed to cancel agent task')
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
    fetchActiveChatJob,
    cancelActiveChat,
    fetchTimeline,
    fetchPRChecklist,
    fetchCodeReviewStatus,
    overrideCodeReview,
    requestReassignment,
    dismissPhaseFailure,
    retryAgentTask,
    cancelAgentTask,
    cancelDesign,
    fetchEstimates,
    recalculateEstimates,
    overrideEstimate,
  }
})
