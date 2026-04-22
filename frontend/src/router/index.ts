// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

import { createRouter, createWebHistory } from 'vue-router'
import api from '@/services/api'
import { useAuthStore } from '@/stores/auth'

let setupChecked = false
let isSetupComplete = false

/** Call after setup completes so the next navigation re-checks the backend. */
export function resetSetupCache(): void {
  setupChecked = false
  isSetupComplete = false
}

async function checkSetupStatus(): Promise<boolean> {
  // Return cached result for subsequent in-session navigations
  if (setupChecked) return isSetupComplete

  // Always verify against backend on first navigation
  try {
    const { data } = await api.get('/setup/status')
    isSetupComplete = data.is_setup_complete === true
    // Sync localStorage with backend truth
    if (isSetupComplete) {
      localStorage.setItem('bodhiorchard_setup_complete', 'true')
    } else {
      localStorage.removeItem('bodhiorchard_setup_complete')
    }
  } catch {
    // Backend unreachable — fall back to localStorage as last resort
    isSetupComplete = localStorage.getItem('bodhiorchard_setup_complete') === 'true'
  }

  setupChecked = true
  return isSetupComplete
}

/** Public routes that don't require authentication. */
const PUBLIC_ROUTES = new Set(['setup', 'login', 'methodology', 'tree-demo', 'house-demo'])

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      redirect: '/methodology',
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
    },
    {
      path: '/setup',
      component: () => import('@/layouts/SetupLayout.vue'),
      children: [
        {
          path: '',
          name: 'setup',
          component: () => import('@/views/setup/SetupWizard.vue'),
        },
      ],
    },
    {
      path: '/change-password',
      name: 'change-password',
      component: () => import('@/views/ChangePasswordView.vue'),
    },
    {
      path: '/methodology',
      name: 'methodology',
      component: () => import('@/views/methodology/MethodologyView.vue'),
    },
    {
      path: '/character-select',
      name: 'character-select',
      component: () => import('@/views/character/CharacterSelectView.vue'),
    },
    {
      path: '/tree-demo',
      name: 'tree-demo',
      component: () => import('@/views/test/TreeTestView.vue'),
    },
    {
      path: '/house-demo',
      name: 'house-demo',
      component: () => import('@/views/test/HouseTestView.vue'),
    },
    {
      path: '/',
      component: () => import('@/layouts/AppLayout.vue'),
      children: [
        {
          path: 'dashboard',
          name: 'dashboard',
          component: () => import('@/views/dashboard/DashboardView.vue'),
        },
        {
          path: 'buds',
          name: 'buds',
          component: () => import('@/views/buds/BUDBoard.vue'),
        },
        {
          path: 'buds/:id',
          name: 'bud-detail',
          component: () => import('@/views/buds/BUDDetail.vue'),
        },
        {
          path: 'features',
          name: 'features',
          component: () => import('@/views/features/FeaturesView.vue'),
        },
        {
          path: 'bugs',
          name: 'bugs',
          component: () => import('@/views/bugs/BugsView.vue'),
        },
        {
          path: 'leaderboard',
          name: 'leaderboard',
          component: () => import('@/views/leaderboard/LeaderboardView.vue'),
        },
        {
          path: 'profile',
          name: 'profile',
          component: () => import('@/views/profile/ProfileView.vue'),
        },
        {
          // Self-service MCP token management. No permission gate — any
          // authenticated user can generate their own token. Hits the
          // new /v1/me/mcp-token backend endpoint, which writes only to
          // the user_mcp_tokens row and never touches the org-level hash.
          path: 'profile/mcp-token',
          name: 'profile-mcp-token',
          component: () => import('@/views/profile/ProfileMcpToken.vue'),
        },
        {
          path: 'skills',
          name: 'skills',
          component: () => import('@/views/skills/SkillProfilesView.vue'),
        },
        {
          path: 'triage',
          name: 'triage',
          meta: { permission: 'backlog:approve' },
          component: () => import('@/views/triage/TriageQueueView.vue'),
        },
        {
          path: 'members',
          name: 'members',
          meta: { permission: 'team:manage' },
          component: () => import('@/views/members/MembersView.vue'),
        },
        {
          path: 'settings',
          name: 'settings',
          meta: { permission: 'integrations:view' },
          component: () => import('@/views/settings/SettingsConnections.vue'),
        },
        {
          path: 'settings/design-systems',
          name: 'settings-design-systems',
          meta: { permission: 'integrations:configure' },
          component: () => import('@/views/settings/SettingsDesignSystems.vue'),
        },
        {
          path: 'settings/agent-prompts',
          name: 'settings-agent-prompts',
          meta: { permission: 'agents:configure' },
          component: () => import('@/views/settings/SettingsAgentPrompts.vue'),
        },
        {
          path: 'settings/qa-automation',
          name: 'settings-qa-automation',
          meta: { permission: 'integrations:configure' },
          component: () => import('@/views/settings/SettingsQAAutomation.vue'),
        },
        {
          path: 'settings/presence',
          name: 'settings-presence',
          meta: { permission: 'integrations:configure' },
          component: () => import('@/views/settings/SettingsPresence.vue'),
        },
        {
          path: 'settings/jira-import',
          name: 'settings-jira-import',
          meta: { permission: 'integrations:configure' },
          component: () => import('@/views/settings/SettingsJiraImport.vue'),
        },
        {
          path: 'raceview/:roomId',
          name: 'race-view',
          component: () => import('@/views/race/RaceRoomView.vue'),
          props: true,
        },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const done = await checkSetupStatus()

  // Setup not done — force to setup wizard
  if (!done && to.name !== 'setup') {
    return { name: 'setup' }
  }

  // Setup done — don't allow going back to setup
  if (done && to.name === 'setup') {
    return { name: 'methodology' }
  }

  // Auth guard — require token for protected routes
  if (done && !PUBLIC_ROUTES.has(to.name as string)) {
    const hasToken = !!localStorage.getItem('bodhiorchard_token')
    if (!hasToken) {
      return { name: 'login' }
    }
  }

  // Already logged in — redirect away from login
  if (to.name === 'login' && localStorage.getItem('bodhiorchard_token')) {
    return { name: 'methodology' }
  }

  // Permission guard — redirect to dashboard if user lacks required permission
  const requiredPerm = to.meta?.permission as string | string[] | undefined
  if (requiredPerm) {
    const authStore = useAuthStore()
    // On page refresh, user is null but token exists — load profile first
    if (!authStore.user && localStorage.getItem('bodhiorchard_token')) {
      try {
        await authStore.fetchUser()
      } catch {
        // Profile load failed — fall through with empty permissions
      }
    }
    const perms = authStore.user?.permissions ?? []
    const allowed = Array.isArray(requiredPerm)
      ? requiredPerm.some(p => perms.includes(p))
      : perms.includes(requiredPerm)
    if (!allowed) {
      return { name: 'dashboard' }
    }
  }
})

export default router
