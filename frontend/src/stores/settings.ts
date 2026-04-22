// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import api from '@/services/api'
import { extractApiError } from '@/utils/errors'
import type { RepoBranchList, RepoInfo } from '@/types'

export interface ConnectionsState {
  sourceCode: {
    localPath: string
    type: 'workspace' | 'single-repo'
  }
  github: { enabled: boolean; appId: number | null; hasPrivateKey: boolean; installationId: number | null; webhookConfigured: boolean; org?: string | null }
  slack: { enabled: boolean; botToken: string; signingSecret: string; teamId: string }
  aiConfig: {
    preset: string
  }
  scan: {
    timeoutSeconds: number
    maxTurns: number
    autoCreateMembers: boolean
  }
  // Per-org QA automation settings. Must track the backend
  // QAAutomationSettings Pydantic model — see backend/app/schemas/settings.py.
  // Kept in snake_case fields because FastAPI emits canonical names on GET
  // and we PATCH the same shape back.
  qaAutomation: {
    enabled: boolean
    framework: string
    bugRejectThreshold: number
  }
  // Per-org BUD lifecycle stage toggles.
  budStages: {
    uatEnabled: boolean
  }
  // Per-org presence / auto-mode settings. Mirrors the backend
  // PresenceSettings Pydantic model (by_alias=True envelope). The
  // `timezone: null` sentinel means "use server local time" which
  // is the legacy behaviour — setting a concrete IANA name opts in
  // to timezone-aware rules everywhere (multiplayer sim + Slack cache).
  presence: {
    autoModeEnabled: boolean
    workingDays: Array<'mon' | 'tue' | 'wed' | 'thu' | 'fri' | 'sat' | 'sun'>
    workingHoursStart: string  // "HH:MM" 24-hour
    workingHoursEnd: string    // "HH:MM" 24-hour
    timezone: string | null
  }
}

function emptyState(): ConnectionsState {
  return {
    sourceCode: { localPath: '', type: 'single-repo' },
    github: { enabled: false, appId: null, hasPrivateKey: false, installationId: null, webhookConfigured: false },
    slack: { enabled: false, botToken: '', signingSecret: '', teamId: '' },
    aiConfig: {
      preset: 'claude-code',
    },
    scan: {
      timeoutSeconds: 300,
      maxTurns: 40,
      autoCreateMembers: true,
    },
    // Defaults mirror backend QAAutomationSettings / BUDStageSettings defaults.
    // If the backend ships a different default, update BOTH or get_connections
    // will overwrite whatever we initialize here on first fetch anyway.
    qaAutomation: {
      enabled: true,
      framework: 'playwright',
      bugRejectThreshold: 5,
    },
    budStages: {
      uatEnabled: true,
    },
    // Defaults mirror backend PresenceSettings defaults — Mon-Fri, 08:00-18:00,
    // timezone null (= use server time). These are overwritten by the first
    // fetchConnections() anyway, but keep the shape non-null for reactivity.
    presence: {
      autoModeEnabled: true,
      workingDays: ['mon', 'tue', 'wed', 'thu', 'fri'],
      workingHoursStart: '08:00',
      workingHoursEnd: '18:00',
      timezone: null,
    },
  }
}

export const useSettingsStore = defineStore('settings', () => {
  const connections = ref<ConnectionsState>(emptyState())
  const loading = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)
  const saveSuccess = ref(false)

  async function fetchConnections(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get('/v1/settings/connections')
      connections.value = data
    } catch (err) {
      error.value = extractApiError(err, 'Failed to load settings.')
    } finally {
      loading.value = false
    }
  }

  async function saveConnections(): Promise<boolean> {
    saving.value = true
    error.value = null
    saveSuccess.value = false
    try {
      const { data } = await api.patch('/v1/settings/connections', connections.value)
      connections.value = data
      saveSuccess.value = true
      return true
    } catch (err) {
      error.value = extractApiError(err, 'Failed to save settings.')
      return false
    } finally {
      saving.value = false
    }
  }

  // Repo management
  const repos = ref<RepoInfo[]>([])
  const reposLoading = ref(false)

  async function fetchRepos(): Promise<void> {
    reposLoading.value = true
    try {
      const { data } = await api.get('/v1/settings/repos')
      repos.value = data
    } catch (err) {
      error.value = extractApiError(err, 'Failed to load repositories.')
    } finally {
      reposLoading.value = false
    }
  }

  async function addRepo(path: string): Promise<boolean> {
    try {
      await api.post('/v1/settings/repos', { path })
      await fetchRepos()
      return true
    } catch (err) {
      error.value = extractApiError(err, 'Failed to add repository.')
      return false
    }
  }

  async function cloneRepo(url: string, pat: string | null = null): Promise<boolean> {
    // Authenticated counterpart of the setup wizard's clone step. The
    // backend clones into /data/repos/<org-slug>/<repo> and registers the
    // tracked_repositories row in one shot, so the UI gets the same
    // "repo now appears in the list" outcome as a local-path add.
    try {
      await api.post('/v1/settings/repos/clone', {
        url,
        pat: pat || undefined,
      }, { timeout: 120_000 })
      await fetchRepos()
      return true
    } catch (err) {
      error.value = extractApiError(err, 'Failed to clone repository.')
      return false
    }
  }

  async function removeRepo(path: string): Promise<boolean> {
    try {
      await api.delete('/v1/settings/repos', { data: { path } })
      await fetchRepos()
      return true
    } catch (err) {
      error.value = extractApiError(err, 'Failed to remove repository.')
      return false
    }
  }

  async function setRepoStatus(repoId: string, status: 'active' | 'ignored'): Promise<boolean> {
    try {
      await api.patch(`/v1/settings/repos/${repoId}/status`, { status })
      await fetchRepos()
      return true
    } catch (err) {
      error.value = extractApiError(err, 'Failed to update repository status.')
      return false
    }
  }

  async function fetchRepoBranches(repoId: string): Promise<RepoBranchList | null> {
    try {
      const { data } = await api.get(`/v1/settings/repos/${repoId}/branches`)
      return data
    } catch (err) {
      error.value = extractApiError(err, 'Failed to load branches.')
      return null
    }
  }

  async function updateRepoBranches(
    repoId: string,
    mainBranch: string | null,
    developBranch: string | null,
    uatBranch: string | null = null,
  ): Promise<boolean> {
    try {
      await api.patch(`/v1/settings/repos/${repoId}/branches`, {
        mainBranch,
        developBranch,
        // Send empty string instead of null when the user clears it,
        // so the backend distinguishes "intentionally cleared" from
        // "field omitted" (the omitted case is just leave-as-is).
        uatBranch: uatBranch ?? '',
      })
      await fetchRepos()
      return true
    } catch (err) {
      error.value = extractApiError(err, 'Failed to update branch mapping.')
      return false
    }
  }

  const allReposMapped = computed(() =>
    repos.value.length > 0 &&
    repos.value
      .filter(r => r.status === 'active')
      .every(r => r.mainBranch !== null && r.developBranch !== null),
  )

  return {
    connections,
    loading,
    saving,
    error,
    saveSuccess,
    fetchConnections,
    saveConnections,
    repos,
    reposLoading,
    fetchRepos,
    addRepo,
    cloneRepo,
    removeRepo,
    setRepoStatus,
    fetchRepoBranches,
    updateRepoBranches,
    allReposMapped,
  }
})
