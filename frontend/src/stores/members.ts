import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'

export interface Member {
  id: string
  email: string
  name: string
  role: string
  roleId: string | null
  roleName: string | null
  createdAt: string
}

export interface RoleOption {
  id: string
  name: string
  description: string | null
}

export const useMembersStore = defineStore('members', () => {
  const members = ref<Member[]>([])
  const roles = ref<RoleOption[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchMembers(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get('/v1/members')
      members.value = data
    } catch {
      error.value = 'Failed to load members.'
    } finally {
      loading.value = false
    }
  }

  async function fetchRoles(): Promise<void> {
    try {
      const { data } = await api.get('/v1/roles')
      roles.value = data.map((r: { id: string; name: string; description: string | null }) => ({
        id: r.id,
        name: r.name,
        description: r.description,
      }))
    } catch {
      // Roles endpoint may require permissions — fail silently
    }
  }

  async function assignRole(userId: string, roleId: string): Promise<boolean> {
    error.value = null
    try {
      const { data } = await api.patch(`/v1/members/${userId}/role`, { roleId })
      const idx = members.value.findIndex(m => m.id === userId)
      if (idx !== -1) members.value[idx] = data
      return true
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { detail?: string } } }
        error.value = axiosErr.response?.data?.detail || 'Failed to assign role.'
      }
      return false
    }
  }

  return {
    members,
    roles,
    loading,
    error,
    fetchMembers,
    fetchRoles,
    assignRole,
  }
})
