import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'
import { extractApiError } from '@/utils/errors'
import { useAuthStore } from '@/stores/auth'

export interface Member {
  id: string
  email: string
  name: string
  role: string
  roleId: string | null
  roleName: string | null
  avatarUrl: string | null
  githubUsername: string | null
  slackId: string | null
  isActive: boolean
  mustChangePassword: boolean
  createdAt: string
  emailAliases: string[]
}

export interface RoleOption {
  id: string
  name: string
  description: string | null
  scopeType: string
  permissions: PermissionItem[]
}

export interface PermissionItem {
  id: string
  name: string
  resourceId: string
  description: string | null
  categoryKey: string
}

export interface PermissionCategory {
  key: string
  name: string
  description: string | null
  permissions: PermissionItem[]
}

export const useMembersStore = defineStore('members', () => {
  const members = ref<Member[]>([])
  const roles = ref<RoleOption[]>([])
  const permissionCategories = ref<PermissionCategory[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchMembers(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get('/v1/members')
      members.value = data
    } catch (err) {
      error.value = extractApiError(err, 'Failed to load members.')
    } finally {
      loading.value = false
    }
  }

  async function fetchRoles(): Promise<void> {
    try {
      const { data } = await api.get('/v1/roles')
      roles.value = data.map((r: Record<string, unknown>) => ({
        id: r.id as string,
        name: r.name as string,
        description: (r.description as string | null) ?? null,
        scopeType: ((r.scopeType as string) ?? (r.scope_type as string) ?? 'system').toUpperCase(),
        permissions: (r.permissions as PermissionItem[]) ?? [],
      }))
    } catch (err) {
      console.warn('[members] fetchRoles failed:', (err as { response?: { status?: number } })?.response?.status)
    }
  }

  async function fetchPermissions(): Promise<void> {
    try {
      const { data } = await api.get('/v1/permissions')
      permissionCategories.value = data.map((cat: PermissionCategory) => ({
        key: cat.key,
        name: cat.name,
        description: cat.description,
        permissions: cat.permissions ?? [],
      }))
    } catch (err) {
      console.warn('[members] fetchPermissions failed:', (err as { response?: { status?: number } })?.response?.status)
    }
  }

  /** Refresh the current user's permissions (call after any role mutation). */
  async function refreshCurrentUserPermissions(): Promise<void> {
    try {
      await useAuthStore().fetchUser()
    } catch {
      // Non-critical — permissions will refresh on next page load
    }
  }

  async function addMember(payload: {
    email: string
    name: string
    password: string
    roleId?: string
    avatarUrl?: string
    githubUsername?: string
  }): Promise<boolean> {
    error.value = null
    try {
      const { data } = await api.post('/v1/members', payload)
      members.value.push(data)
      return true
    } catch (err) {
      error.value = extractApiError(err, 'Failed to add member.')
      return false
    }
  }

  async function toggleMemberStatus(userId: string): Promise<boolean> {
    error.value = null
    try {
      const { data } = await api.patch(`/v1/members/${userId}/status`)
      const idx = members.value.findIndex(m => m.id === userId)
      if (idx !== -1) members.value[idx] = data
      return true
    } catch (err) {
      error.value = extractApiError(err, 'Failed to update status.')
      return false
    }
  }

  async function assignRole(userId: string, roleId: string): Promise<boolean> {
    error.value = null
    try {
      const { data } = await api.patch(`/v1/members/${userId}/role`, { roleId })
      const idx = members.value.findIndex(m => m.id === userId)
      if (idx !== -1) members.value[idx] = data
      await refreshCurrentUserPermissions()
      return true
    } catch (err) {
      error.value = extractApiError(err, 'Failed to assign role.')
      return false
    }
  }

  async function createRole(payload: {
    name: string
    description?: string
    permission_ids: string[]
  }): Promise<boolean> {
    error.value = null
    try {
      await api.post('/v1/roles', payload)
      await fetchRoles()
      return true
    } catch (err) {
      error.value = extractApiError(err, 'Failed to create role.')
      return false
    }
  }

  async function updateRole(
    roleId: string,
    payload: { name?: string; description?: string; permission_ids?: string[] },
  ): Promise<boolean> {
    error.value = null
    try {
      await api.put(`/v1/roles/${roleId}`, payload)
      await fetchRoles()
      await refreshCurrentUserPermissions()
      return true
    } catch (err) {
      error.value = extractApiError(err, 'Failed to update role.')
      return false
    }
  }

  async function mergeMember(targetId: string, sourceId: string): Promise<boolean> {
    error.value = null
    try {
      await api.post(`/v1/members/${targetId}/merge`, { sourceId })
      await fetchMembers()
      return true
    } catch (err) {
      error.value = extractApiError(err, 'Failed to merge members.')
      return false
    }
  }

  async function updateCharacter(
    userId: string,
    characterModel: string | null,
  ): Promise<boolean> {
    error.value = null
    try {
      const { data } = await api.patch(`/v1/members/${userId}/character`, {
        characterModel,
      })
      const idx = members.value.findIndex(m => m.id === userId)
      if (idx !== -1) members.value[idx] = data
      return true
    } catch (err) {
      error.value = extractApiError(err, 'Failed to update character.')
      return false
    }
  }

  interface SetPasswordResult {
    password: string
    loginUrl: string
    slackSent?: boolean | null
    slackError?: string | null
  }

  async function setPassword(
    userId: string,
    sendVia?: 'slack',
  ): Promise<SetPasswordResult | null> {
    error.value = null
    try {
      const payload = sendVia ? { sendVia } : {}
      const { data } = await api.post(`/v1/members/${userId}/set-password`, payload)
      const idx = members.value.findIndex(m => m.id === userId)
      if (idx !== -1) members.value[idx].mustChangePassword = true
      return {
        password: data.password,
        loginUrl: data.loginUrl ?? '',
        slackSent: data.slackSent ?? null,
        slackError: data.slackError ?? null,
      }
    } catch (err) {
      error.value = extractApiError(err, 'Failed to set password.')
      return null
    }
  }

  async function deleteRole(roleId: string): Promise<boolean> {
    error.value = null
    try {
      await api.delete(`/v1/roles/${roleId}`)
      roles.value = roles.value.filter(r => r.id !== roleId)
      await refreshCurrentUserPermissions()
      return true
    } catch (err) {
      error.value = extractApiError(err, 'Failed to delete role.')
      return false
    }
  }

  return {
    members,
    roles,
    permissionCategories,
    loading,
    error,
    fetchMembers,
    fetchRoles,
    fetchPermissions,
    addMember,
    toggleMemberStatus,
    assignRole,
    mergeMember,
    updateCharacter,
    setPassword,
    createRole,
    updateRole,
    deleteRole,
  }
})
