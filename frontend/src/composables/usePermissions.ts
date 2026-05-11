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
  const canViewJiraImport = computed(() => hasPermission('integrations:configure'))
  // /settings/code hosts repository import (and later, scan controls).
  // Same gate as the other configure pages so visibility tracks edit
  // ability rather than splitting view-only access from action access.
  const canViewCodeSettings = computed(() => hasPermission('integrations:configure'))

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
    canViewJiraImport,
    canViewCodeSettings,
  }
}
