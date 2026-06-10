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
import { computed, ref } from 'vue'
import api from '@/services/api'
import { extractApiError } from '@/utils/errors'

export type TeamStatus = 'active' | 'archived'

export interface TeamMemberRead {
  user_id: string
  name: string
  email: string
  role: string
  role_name: string | null
  avatar_url: string | null
  is_active: boolean
}

export interface TeamRepoRead {
  repo_id: string
  name: string
  path: string
  github_full_name: string | null
}

export interface TeamRead {
  id: string
  name: string
  description: string | null
  status: TeamStatus
  members: TeamMemberRead[]
  repos: TeamRepoRead[]
}

export interface TeamSummary {
  id: string
  name: string
  status: TeamStatus
}

export const useTeamsStore = defineStore('teams', () => {
  // Summary list for the Settings → Teams table and the BUDBoard filter.
  // Full ``TeamRead`` rows live in ``detailsById`` so the detail panel
  // doesn't refetch on every selection change.
  const teams = ref<TeamSummary[]>([])
  const detailsById = ref<Record<string, TeamRead>>({})
  const loading = ref(false)
  const error = ref<string | null>(null)

  const activeTeams = computed(() => teams.value.filter(t => t.status === 'active'))

  async function fetchTeams(includeArchived = false): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get<TeamSummary[]>('/v1/teams', {
        params: { include_archived: includeArchived },
      })
      teams.value = data
    } catch (e) {
      error.value = extractApiError(e, 'Team operation failed.')
    } finally {
      loading.value = false
    }
  }

  async function fetchTeam(teamId: string): Promise<TeamRead | null> {
    try {
      const { data } = await api.get<TeamRead>(`/v1/teams/${teamId}`)
      detailsById.value = { ...detailsById.value, [teamId]: data }
      return data
    } catch (e) {
      error.value = extractApiError(e, 'Team operation failed.')
      return null
    }
  }

  async function createTeam(body: {
    name: string
    description?: string | null
  }): Promise<TeamRead | null> {
    try {
      const { data } = await api.post<TeamRead>('/v1/teams', body)
      detailsById.value = { ...detailsById.value, [data.id]: data }
      // Optimistic insert into the summary list so the UI updates
      // without a full re-fetch.
      teams.value = [...teams.value, { id: data.id, name: data.name, status: data.status }]
        .sort((a, b) => a.name.localeCompare(b.name))
      return data
    } catch (e) {
      error.value = extractApiError(e, 'Team operation failed.')
      return null
    }
  }

  async function updateTeam(
    teamId: string,
    body: { name?: string; description?: string | null; status?: TeamStatus },
  ): Promise<TeamRead | null> {
    try {
      const { data } = await api.patch<TeamRead>(`/v1/teams/${teamId}`, body)
      detailsById.value = { ...detailsById.value, [teamId]: data }
      teams.value = teams.value
        .map(t => (t.id === teamId ? { id: data.id, name: data.name, status: data.status } : t))
        .sort((a, b) => a.name.localeCompare(b.name))
      return data
    } catch (e) {
      error.value = extractApiError(e, 'Team operation failed.')
      return null
    }
  }

  async function archiveTeam(teamId: string): Promise<boolean> {
    try {
      await api.delete(`/v1/teams/${teamId}`)
      teams.value = teams.value.map(t =>
        t.id === teamId ? { ...t, status: 'archived' as TeamStatus } : t,
      )
      const detail = detailsById.value[teamId]
      if (detail) {
        detailsById.value = {
          ...detailsById.value,
          [teamId]: { ...detail, status: 'archived' },
        }
      }
      return true
    } catch (e) {
      error.value = extractApiError(e, 'Team operation failed.')
      return false
    }
  }

  async function addMember(teamId: string, userId: string): Promise<TeamRead | null> {
    try {
      const { data } = await api.post<TeamRead>(`/v1/teams/${teamId}/members`, {
        user_id: userId,
      })
      detailsById.value = { ...detailsById.value, [teamId]: data }
      return data
    } catch (e) {
      error.value = extractApiError(e, 'Team operation failed.')
      return null
    }
  }

  async function removeMember(teamId: string, userId: string): Promise<boolean> {
    try {
      await api.delete(`/v1/teams/${teamId}/members/${userId}`)
      const detail = detailsById.value[teamId]
      if (detail) {
        detailsById.value = {
          ...detailsById.value,
          [teamId]: { ...detail, members: detail.members.filter(m => m.user_id !== userId) },
        }
      }
      return true
    } catch (e) {
      error.value = extractApiError(e, 'Team operation failed.')
      return false
    }
  }

  async function addRepo(teamId: string, repoId: string): Promise<TeamRead | null> {
    try {
      const { data } = await api.post<TeamRead>(`/v1/teams/${teamId}/repos`, {
        repo_id: repoId,
      })
      detailsById.value = { ...detailsById.value, [teamId]: data }
      return data
    } catch (e) {
      error.value = extractApiError(e, 'Team operation failed.')
      return null
    }
  }

  async function removeRepo(teamId: string, repoId: string): Promise<boolean> {
    try {
      await api.delete(`/v1/teams/${teamId}/repos/${repoId}`)
      const detail = detailsById.value[teamId]
      if (detail) {
        detailsById.value = {
          ...detailsById.value,
          [teamId]: { ...detail, repos: detail.repos.filter(r => r.repo_id !== repoId) },
        }
      }
      return true
    } catch (e) {
      error.value = extractApiError(e, 'Team operation failed.')
      return false
    }
  }

  return {
    teams,
    detailsById,
    loading,
    error,
    activeTeams,
    fetchTeams,
    fetchTeam,
    createTeam,
    updateTeam,
    archiveTeam,
    addMember,
    removeMember,
    addRepo,
    removeRepo,
  }
})
