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
 * The settings pages, grouped for the section list beside Settings →
 * Integrations. Each entry carries the permission check its route uses,
 * so the list only shows pages the reader can open.
 */

export type SettingsPermission =
  | 'connections'
  | 'code'
  | 'designSystems'
  | 'agentPrompts'
  | 'qa'
  | 'presence'
  | 'jira'
  | 'quiz'
  | 'leave'
  | 'employees'
  | 'celebrations'
  | 'members'
  | 'engineering'

export interface SettingsLink {
  title: string
  to: string
  needs: SettingsPermission
}

export interface SettingsGroup {
  label: string
  items: SettingsLink[]
}

const GROUPS: SettingsGroup[] = [
  {
    label: 'Workspace',
    items: [
      { title: 'Integrations', to: '/settings', needs: 'connections' },
      { title: 'Teams', to: '/members?tab=teams', needs: 'members' },
      { title: 'Offices', to: '/settings/offices', needs: 'employees' },
    ],
  },
  {
    label: 'Agents',
    items: [
      { title: 'Code and repositories', to: '/settings/code', needs: 'code' },
      { title: 'Agent prompts', to: '/settings/agent-prompts', needs: 'agentPrompts' },
      { title: 'QA automation', to: '/settings/qa-automation', needs: 'qa' },
      { title: 'Design systems', to: '/settings/design-systems', needs: 'designSystems' },
      { title: 'MCP connect', to: '/settings/mcp-connect', needs: 'engineering' },
    ],
  },
  {
    label: 'People',
    items: [
      { title: 'Leave policies', to: '/settings/leave', needs: 'leave' },
      { title: 'Celebrations', to: '/settings/celebrations', needs: 'celebrations' },
      { title: 'Presence', to: '/settings/presence', needs: 'presence' },
    ],
  },
  {
    label: 'Extras',
    items: [
      { title: 'Quiz game', to: '/settings/quiz-game', needs: 'quiz' },
      { title: 'Quiz review', to: '/settings/quiz-review', needs: 'quiz' },
      { title: 'Jira import', to: '/settings/jira-import', needs: 'jira' },
    ],
  },
]

/** The groups the reader can open, with empty groups dropped. */
export function settingsSections(can: Record<SettingsPermission, boolean>): SettingsGroup[] {
  return GROUPS.map(g => ({ ...g, items: g.items.filter(i => can[i.needs]) })).filter(g => g.items.length > 0)
}
