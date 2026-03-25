import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'

export function usePermissions() {
  const authStore = useAuthStore()

  function hasPermission(permission: string): boolean {
    return authStore.user?.permissions?.includes(permission) ?? false
  }

  function hasAnyPermission(...permissions: string[]): boolean {
    return permissions.some(p => hasPermission(p))
  }

  // Sidebar visibility
  const canApprove = computed(() => hasPermission('backlog:approve'))
  const canManageMembers = computed(() => hasPermission('team:manage'))
  const canViewSettings = computed(() =>
    hasAnyPermission('org:view_settings', 'integrations:view'),
  )
  const canViewConnections = computed(() => hasPermission('integrations:view'))
  const canViewDesignSystems = computed(() => hasPermission('integrations:configure'))
  const canViewAgentPrompts = computed(() => hasPermission('agents:configure'))

  return {
    hasPermission,
    hasAnyPermission,
    canApprove,
    canManageMembers,
    canViewSettings,
    canViewConnections,
    canViewDesignSystems,
    canViewAgentPrompts,
  }
}
