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
import type { BUDPriority } from '@/types'
import { extractApiError } from '@/utils/errors'

export interface TriageSession {
  id: string
  org_id: string
  slack_channel: string
  thread_ts: string
  requester_slack_id: string
  requester_name: string | null
  requester_display_name: string | null
  original_text: string | null
  status: string
  priority: string | null
  /** The priority the BUD gets if the request is approved (the backend's normalised ``priority``). */
  bud_priority: BUDPriority
  feature_name: string | null
  triage_context: Record<string, unknown> | null
  bud_id: string | null
  created_at: string
  updated_at: string
}

export const WAITING_STATUS = 'awaiting_pm'
/** Statuses a request ends in once someone has decided on it. */
export const DECIDED_STATUSES = ['bud_created', 'approved', 'rejected'] as const

function newestFirst(a: TriageSession, b: TriageSession): number {
  return b.created_at.localeCompare(a.created_at)
}

export const useTriageStore = defineStore('triage', () => {
  /** Requests waiting for a decision. */
  const sessions = ref<TriageSession[]>([])
  /** Decided requests; loaded on demand. */
  const history = ref<TriageSession[]>([])
  const historyLoaded = ref(false)
  const loading = ref(false)
  /** A failed load. */
  const error = ref('')
  /** A failed approve or reject, shown where the decision was made. */
  const actionError = ref('')

  async function list(status: string): Promise<TriageSession[]> {
    const { data } = await api.get<TriageSession[]>('/v1/triage-sessions/', { params: { status } })
    return data
  }

  async function fetchSessions(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      sessions.value = await list(WAITING_STATUS)
    } catch (err) {
      error.value = extractApiError(err, 'Failed to load triage requests.')
    } finally {
      loading.value = false
    }
  }

  // The endpoint filters on one status, so history is one request per
  // decided status, merged.
  async function fetchHistory(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      const lists = await Promise.all(DECIDED_STATUSES.map(list))
      history.value = lists.flat().sort(newestFirst)
      historyLoaded.value = true
    } catch (err) {
      error.value = extractApiError(err, 'Failed to load earlier requests.')
    } finally {
      loading.value = false
    }
  }

  // A decided request leaves the waiting list and joins the history.
  function settle(decided: TriageSession): void {
    sessions.value = sessions.value.filter(s => s.id !== decided.id)
    if (historyLoaded.value) history.value = [decided, ...history.value.filter(s => s.id !== decided.id)]
  }

  async function decide(id: string, action: 'approve' | 'reject', notes?: string): Promise<boolean> {
    actionError.value = ''
    try {
      const body = notes ? { notes } : undefined
      const { data } = await api.post<TriageSession>(`/v1/triage-sessions/${id}/${action}`, body)
      settle(data)
      return true
    } catch (err) {
      actionError.value = extractApiError(err, action === 'approve' ? 'Failed to create the BUD.' : 'Failed to reject the request.')
      return false
    }
  }

  const approveSession = (id: string, notes?: string): Promise<boolean> => decide(id, 'approve', notes)
  const rejectSession = (id: string, notes?: string): Promise<boolean> => decide(id, 'reject', notes)

  return {
    sessions,
    history,
    historyLoaded,
    loading,
    error,
    actionError,
    fetchSessions,
    fetchHistory,
    approveSession,
    rejectSession,
  }
})
