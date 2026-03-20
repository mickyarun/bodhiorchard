import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'
import type { RepoInfo } from '@/types'

export interface ConnectionsState {
  sourceCode: {
    localPath: string
    type: 'workspace' | 'single-repo'
  }
  github: { enabled: boolean; pat: string }
  slack: { enabled: boolean; botToken: string; signingSecret: string }
  aiConfig: {
    preset: string
    ollamaUrl: string
    ollamaModel: string
    cloudProvider: string
    cloudApiKey: string
    cloudModel: string
  }
  scan: {
    timeoutSeconds: number
    maxTurns: number
  }
}

function emptyState(): ConnectionsState {
  return {
    sourceCode: { localPath: '', type: 'single-repo' },
    github: { enabled: false, pat: '' },
    slack: { enabled: false, botToken: '', signingSecret: '' },
    aiConfig: {
      preset: 'hybrid',
      ollamaUrl: 'http://localhost:11434',
      ollamaModel: 'llama3:8b',
      cloudProvider: 'anthropic',
      cloudApiKey: '',
      cloudModel: 'claude-sonnet-4-5-20250514',
    },
    scan: {
      timeoutSeconds: 300,
      maxTurns: 40,
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
    } catch {
      error.value = 'Failed to load settings.'
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
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { detail?: string } } }
        error.value = axiosErr.response?.data?.detail || 'Failed to save settings.'
      } else {
        error.value = 'Network error. Please check your connection.'
      }
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
    } catch {
      error.value = 'Failed to load repositories.'
    } finally {
      reposLoading.value = false
    }
  }

  async function addRepo(path: string): Promise<boolean> {
    try {
      await api.post('/v1/settings/repos', { path })
      await fetchRepos()
      return true
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { detail?: string } } }
        error.value = axiosErr.response?.data?.detail || 'Failed to add repository.'
      }
      return false
    }
  }

  async function removeRepo(path: string): Promise<boolean> {
    try {
      await api.delete('/v1/settings/repos', { data: { path } })
      await fetchRepos()
      return true
    } catch {
      error.value = 'Failed to remove repository.'
      return false
    }
  }

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
  }
})
