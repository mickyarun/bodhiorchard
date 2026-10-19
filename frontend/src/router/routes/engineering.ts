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
 * Engineering-workspace routes: everything a people-only role (sales, HR)
 * can't open. Each record is tagged ``meta.workspace = 'engineering'`` and
 * the guard in ``router/guards.ts`` sends users without
 * `workspace:engineering` to their own home instead.
 *
 * The tag lives on its own meta key, not ``meta.permission``, so a route
 * can still declare a finer permission (triage needs ``backlog:approve``)
 * without overwriting the workspace requirement.
 */
import type { RouteRecordRaw } from 'vue-router'

function inEngineeringWorkspace(routes: RouteRecordRaw[]): RouteRecordRaw[] {
  return routes.map(route => ({ ...route, meta: { ...route.meta, workspace: 'engineering' } }))
}

export const engineeringRoutes: RouteRecordRaw[] = inEngineeringWorkspace([
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
    component: () => import('@/views/bugs/BugBoard.vue'),
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
    // Self-service MCP token management for anyone in the engineering
    // workspace. Hits /v1/me/mcp-token, which writes only to the
    // user_mcp_tokens row and never touches the org-level hash.
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
    // Org-level Learnings overview: trends across closed BUDs.
    // Reads the velocity_aggregates rollup + last 50 feature_
    // learnings rows. Visible to every org member — the data is
    // aggregate retrospective info with no cross-tenant exposure
    // (repo queries filter by current_user.org_id).
    path: 'learnings',
    name: 'learnings',
    component: () => import('@/views/learnings/LearningsOverview.vue'),
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
    // Legacy URL: Teams used to live at /settings/teams. They
    // now live as a tab on /members so admins manage people and
    // squads side-by-side. Redirect keeps old bookmarks alive.
    path: 'settings/teams',
    redirect: { name: 'members', query: { tab: 'teams' } },
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
    path: 'settings/quiz-game',
    name: 'settings-quiz-game',
    meta: { permission: 'quiz:configure' },
    component: () => import('@/views/settings/SettingsQuizGame.vue'),
  },
  {
    path: 'settings/quiz-review',
    name: 'settings-quiz-review',
    meta: { permission: 'quiz:configure' },
    component: () => import('@/views/quiz/QuizReviewView.vue'),
  },
  {
    path: 'settings/code',
    name: 'settings-code',
    meta: { permission: 'integrations:configure' },
    component: () => import('@/views/settings/SettingsCode.vue'),
  },
  {
    path: 'settings/mcp-connect',
    name: 'settings-mcp-connect',
    // Self-service for anyone in the engineering workspace: manage
    // their own MCP tokens and copy the connect config for their
    // local AI. No org-level permission gate beyond the workspace.
    component: () => import('@/views/settings/SettingsMCPConnect.vue'),
  },
  {
    path: 'raceview/:roomId',
    name: 'race-view',
    component: () => import('@/views/race/RaceRoomView.vue'),
    props: true,
  },
  {
    path: 'games/backlash/:roomId',
    name: 'backlash-room',
    component: () => import('@/views/backlash/BacklashRoomView.vue'),
    props: true,
  },
])
