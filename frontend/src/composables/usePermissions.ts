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
  // QA Automation page matches the SettingsQAAutomation route guard — same
  // permission gate as the other "configure" pages, so the sidebar entry
  // is visible to the same users who can actually save changes.
  const canViewQAAutomation = computed(() => hasPermission('integrations:configure'))
  // Presence / Auto Mode page mirrors the same "configure" permission —
  // anyone who can touch QA automation can also touch presence settings.
  const canViewPresenceSettings = computed(() => hasPermission('integrations:configure'))

  return {
    hasPermission,
    hasAnyPermission,
    canApprove,
    canManageMembers,
    canViewSettings,
    canViewConnections,
    canViewDesignSystems,
    canViewAgentPrompts,
    canViewQAAutomation,
    canViewPresenceSettings,
  }
}
