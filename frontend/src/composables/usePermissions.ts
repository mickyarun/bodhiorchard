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

  // Org administrators — the org owner and platform admins. Role-based (not a
  // granted permission) because it gates admin-only *detail* like raw play
  // counts on the mini-game leaderboards, which ordinary players shouldn't see.
  const isOrgAdmin = computed(
    () => authStore.user?.role === 'org_owner' || authStore.user?.role === 'admin',
  )

  // Sidebar visibility
  const canApprove = computed(() => hasPermission('backlog:approve'))
  // Gates the "New BUD" affordance. Mirrors the POST /v1/buds backend
  // gate (buds:create) so roles without it — developer, qa, viewer —
  // don't see a button that would 403.
  const canCreateBuds = computed(() => hasPermission('buds:create'))
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

  // Company Quiz Game admin (settings + question review/approval). Gated on a
  // standalone permission so it can be granted to a "Quiz Master" custom role
  // independently of org admin — keeping competing players out of the answers.
  const canManageQuiz = computed(() => hasPermission('quiz:configure'))

  // Bug board. Each helper pairs the new ``bugs:*`` perm with the
  // legacy ``buds:*`` fallback so role tokens minted before the Step E
  // backend rollout don't lose access. Drop the legacy half once the
  // backend's ``TODO(step-e-cleanup)`` is resolved.
  const canViewBugs = computed(() => hasAnyPermission('bugs:view', 'buds:view'))
  const canReportBugs = computed(() => hasAnyPermission('bugs:report', 'buds:edit'))
  const canEditBugs = computed(() => hasAnyPermission('bugs:edit', 'buds:edit'))
  const canAssignBugs = computed(() => hasPermission('bugs:assign'))
  const canCommentOnBugs = computed(() => hasAnyPermission('bugs:comment', 'buds:edit'))

  return {
    hasPermission,
    hasAnyPermission,
    isOrgAdmin,
    canApprove,
    canCreateBuds,
    canManageMembers,
    canViewSettings,
    canViewConnections,
    canViewDesignSystems,
    canViewAgentPrompts,
    canViewQAAutomation,
    canViewPresenceSettings,
    canViewJiraImport,
    canViewCodeSettings,
    canManageQuiz,
    canViewBugs,
    canReportBugs,
    canEditBugs,
    canAssignBugs,
    canCommentOnBugs,
  }
}
