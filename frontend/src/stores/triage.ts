// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'

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
  feature_name: string | null
  triage_context: Record<string, unknown> | null
  bud_id: string | null
  created_at: string
  updated_at: string
}

export const useTriageStore = defineStore('triage', () => {
  const sessions = ref<TriageSession[]>([])
  const loading = ref(false)
  const error = ref('')

  async function fetchSessions(status?: string): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      const params: Record<string, string> = {}
      if (status) params.status = status
      const { data } = await api.get('/v1/triage-sessions/', { params })
      sessions.value = data
    } catch {
      error.value = 'Failed to load triage sessions'
    } finally {
      loading.value = false
    }
  }

  async function approveSession(id: string, notes?: string): Promise<boolean> {
    error.value = ''
    try {
      const body = notes ? { notes } : undefined
      const { data } = await api.post(`/v1/triage-sessions/${id}/approve`, body)
      const idx = sessions.value.findIndex(s => s.id === id)
      if (idx !== -1) sessions.value[idx] = data
      return true
    } catch {
      error.value = 'Failed to approve session'
      return false
    }
  }

  async function rejectSession(id: string, notes?: string): Promise<boolean> {
    error.value = ''
    try {
      const body = notes ? { notes } : undefined
      const { data } = await api.post(`/v1/triage-sessions/${id}/reject`, body)
      const idx = sessions.value.findIndex(s => s.id === id)
      if (idx !== -1) sessions.value[idx] = data
      return true
    } catch {
      error.value = 'Failed to reject session'
      return false
    }
  }

  return {
    sessions,
    loading,
    error,
    fetchSessions,
    approveSession,
    rejectSession,
  }
})
