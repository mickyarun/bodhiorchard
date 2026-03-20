import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'
import type { TeamDetail } from '@/types'

export const useTeamsStore = defineStore('teams', () => {
  const teams = ref<TeamDetail[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchTeams(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get('/v1/teams')
      teams.value = data
    } catch {
      error.value = 'Failed to load teams.'
    } finally {
      loading.value = false
    }
  }

  async function createTeam(name: string, description?: string): Promise<TeamDetail | null> {
    error.value = null
    try {
      const { data } = await api.post('/v1/teams', { name, description })
      teams.value.push(data)
      return data
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { detail?: string } } }
        error.value = axiosErr.response?.data?.detail || 'Failed to create team.'
      }
      return null
    }
  }

  async function deleteTeam(id: string): Promise<boolean> {
    try {
      await api.delete(`/v1/teams/${id}`)
      teams.value = teams.value.filter(t => t.id !== id)
      return true
    } catch {
      error.value = 'Failed to delete team.'
      return false
    }
  }

  async function addMember(
    teamId: string,
    userId: string,
    role: string = 'member',
  ): Promise<boolean> {
    try {
      const { data } = await api.post(`/v1/teams/${teamId}/members`, { userId, role })
      const team = teams.value.find(t => t.id === teamId)
      if (team) {
        team.members.push(data)
        team.memberCount = team.members.length
      }
      return true
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { detail?: string } } }
        error.value = axiosErr.response?.data?.detail || 'Failed to add member.'
      }
      return false
    }
  }

  async function removeMember(teamId: string, userId: string): Promise<boolean> {
    try {
      await api.delete(`/v1/teams/${teamId}/members/${userId}`)
      const team = teams.value.find(t => t.id === teamId)
      if (team) {
        team.members = team.members.filter(m => m.userId !== userId)
        team.memberCount = team.members.length
      }
      return true
    } catch {
      error.value = 'Failed to remove member.'
      return false
    }
  }

  return {
    teams,
    loading,
    error,
    fetchTeams,
    createTeam,
    deleteTeam,
    addMember,
    removeMember,
  }
})
