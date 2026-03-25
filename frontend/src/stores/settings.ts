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
  github: { enabled: boolean; pat: string; org: string; patExpiresAt: string | null }
  slack: { enabled: boolean; botToken: string; signingSecret: string; teamId: string }
  aiConfig: {
    preset: string
  }
  scan: {
    timeoutSeconds: number
    maxTurns: number
    autoCreateMembers: boolean
  }
}

function emptyState(): ConnectionsState {
  return {
    sourceCode: { localPath: '', type: 'single-repo' },
    github: { enabled: false, pat: '', org: '', patExpiresAt: null },
    slack: { enabled: false, botToken: '', signingSecret: '', teamId: '' },
    aiConfig: {
      preset: 'claude-code',
    },
    scan: {
      timeoutSeconds: 300,
      maxTurns: 40,
      autoCreateMembers: true,
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
  ): Promise<boolean> {
    try {
      await api.patch(`/v1/settings/repos/${repoId}/branches`, {
        mainBranch,
        developBranch,
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
    removeRepo,
    setRepoStatus,
    fetchRepoBranches,
    updateRepoBranches,
    allReposMapped,
  }
})
