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

/**
 * Pinia store for the Jira import pipeline.
 *
 * Manages: connection status, project discovery, import sessions,
 * and active import/discovery job tracking.
 */
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import api from '@/services/api'
import { extractApiError } from '@/utils/errors'

// ── Types ────────────────────────────────────────────────────────

export interface JiraProject {
  key: string
  name: string
  lead: string | null
}

export interface IssueTypeCount {
  issueType: string
  count: number
}

export interface DiscoveryResult {
  projectKey: string
  projectName: string
  totalIssues: number
  byType: IssueTypeCount[]
  statusesFound: string[]
  estimatedTimeSeconds: number
  alreadyImportedCount: number
  sampleIssues: Array<{
    key: string
    summary: string
    type: string
    status: string
  }>
}

export interface ImportSession {
  id: string
  jiraProjectKey: string
  jiraProjectName: string
  status: string
  totalIssues: number | null
  processedCount: number
  discoveryResult: DiscoveryResult | null
  result: ReconciliationReport | null
  error: string | null
  jobId: string | null
  createdAt: string
}

export interface ReconciliationReport {
  totalJiraIssues: number
  imported: {
    budsCreated: number
    bugsCreated: number
    consolidatedIntoEpics: number
    subtasksFolded: number
  }
  skipped: {
    exactDuplicates: number
    semanticDuplicates: number
    mergedSimilar: number
  }
  reviewNeeded: Array<{
    jiraKey: string
    summary: string
    descriptionPreview: string
    issueType: string
    similarToBud: number | null
    distance: number
  }>
  failed: Array<{
    jiraKey: string
    error: string
  }>
}

export interface StatusMapping {
  jiraStatus: string
  budStatus: string
}

export interface TypeMapping {
  jiraType: string
  target: 'bud' | 'bug' | 'skip'
}

// ── Store ────────────────────────────────────────────────────────

export const useJiraImportStore = defineStore('jiraImport', () => {
  // Connection state
  const connected = ref(false)
  const siteUrl = ref('')
  const email = ref('')
  const apiToken = ref('')

  // Project listing
  const projects = ref<JiraProject[]>([])

  // Discovery
  const activeSessionId = ref<string | null>(null)
  const discoveryResult = ref<DiscoveryResult | null>(null)

  // Import sessions
  const sessions = ref<ImportSession[]>([])

  // UI state
  const loading = ref(false)
  const saving = ref(false)
  const error = ref<string | null>(null)

  const isConnected = computed(() => connected.value)

  // ── Connection ───────────────────────────────────────────────

  async function fetchConnectionStatus(): Promise<void> {
    try {
      const { data } = await api.get('/v1/settings/connections')
      const jira = data.jira
      if (jira && jira.enabled) {
        connected.value = true
        siteUrl.value = jira.siteUrl || ''
        email.value = jira.email || ''
      } else {
        connected.value = false
      }
    } catch {
      // Silently fail — page will show "not connected" state
    }
  }

  async function testAndSaveConnection(): Promise<boolean> {
    saving.value = true
    error.value = null
    try {
      const { data } = await api.post('/v1/jira/connect', {
        siteUrl: siteUrl.value,
        email: email.value,
        apiToken: apiToken.value,
      })
      connected.value = data.connected
      if (!data.connected) {
        error.value = data.error || 'Connection failed.'
        return false
      }
      // Clear token from reactive state after successful save (encrypted on server)
      apiToken.value = ''
      return true
    } catch (err) {
      error.value = extractApiError(err, 'Failed to connect to Jira.')
      return false
    } finally {
      saving.value = false
    }
  }

  async function disconnect(): Promise<void> {
    try {
      await api.delete('/v1/jira/connect')
      connected.value = false
      siteUrl.value = ''
      email.value = ''
      apiToken.value = ''
      projects.value = []
    } catch (err) {
      error.value = extractApiError(err, 'Failed to disconnect.')
    }
  }

  // ── Projects ─────────────────────────────────────────────────

  async function fetchProjects(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get('/v1/jira/projects')
      projects.value = data
    } catch (err) {
      error.value = extractApiError(err, 'Failed to load Jira projects.')
    } finally {
      loading.value = false
    }
  }

  // ── Discovery ────────────────────────────────────────────────

  async function discoverProject(
    projectKey: string,
    jqlFilter?: string,
  ): Promise<string | null> {
    error.value = null
    try {
      const { data } = await api.post('/v1/jira/discover', {
        projectKey,
        jqlFilter: jqlFilter || null,
      })
      activeSessionId.value = data.sessionId
      return data.jobId
    } catch (err) {
      error.value = extractApiError(err, 'Failed to start discovery.')
      return null
    }
  }

  function setDiscoveryResult(result: DiscoveryResult): void {
    discoveryResult.value = result
  }

  // ── Import ───────────────────────────────────────────────────

  async function startImport(opts: {
    consolidationMode: 'epic' | 'flat'
    statusMappings: StatusMapping[]
    typeMappings: TypeMapping[]
    includeActive?: boolean
  }): Promise<string | null> {
    if (!activeSessionId.value) {
      error.value = 'No active session. Run discovery first.'
      return null
    }
    error.value = null
    try {
      const { data } = await api.post('/v1/jira/import', {
        sessionId: activeSessionId.value,
        consolidationMode: opts.consolidationMode,
        statusMappings: opts.statusMappings,
        typeMappings: opts.typeMappings,
        includeActive: opts.includeActive ?? false,
      })
      return data.jobId
    } catch (err) {
      error.value = extractApiError(err, 'Failed to start import.')
      return null
    }
  }

  // ── Sessions ─────────────────────────────────────────────────

  async function fetchSessions(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get('/v1/jira/sessions')
      sessions.value = data
    } catch (err) {
      error.value = extractApiError(err, 'Failed to load import sessions.')
    } finally {
      loading.value = false
    }
  }

  async function fetchSession(sessionId: string): Promise<ImportSession | null> {
    try {
      const { data } = await api.get(`/v1/jira/sessions/${sessionId}`)
      return data
    } catch (err) {
      error.value = extractApiError(err, 'Failed to load session.')
      return null
    }
  }

  // ── Enrichment ───────────────────────────────────────────────

  async function enrichSession(sessionId: string): Promise<string | null> {
    error.value = null
    try {
      const { data } = await api.post(`/v1/jira/sessions/${sessionId}/enrich`)
      return data.jobId
    } catch (err) {
      error.value = extractApiError(err, 'Failed to start enrichment.')
      return null
    }
  }

  // ── Reset ────────────────────────────────────────────────────

  function resetWizard(): void {
    activeSessionId.value = null
    discoveryResult.value = null
    error.value = null
  }

  return {
    // State
    connected,
    siteUrl,
    email,
    apiToken,
    projects,
    activeSessionId,
    discoveryResult,
    sessions,
    loading,
    saving,
    error,
    // Computed
    isConnected,
    // Actions
    fetchConnectionStatus,
    testAndSaveConnection,
    disconnect,
    fetchProjects,
    discoverProject,
    setDiscoveryResult,
    startImport,
    fetchSessions,
    fetchSession,
    enrichSession,
    resetWizard,
  }
})
