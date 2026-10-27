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

import { describe, expect, it } from 'vitest'
import { settingsSections, type SettingsPermission } from './settingsSections'

const NONE: Record<SettingsPermission, boolean> = {
  connections: false,
  code: false,
  designSystems: false,
  agentPrompts: false,
  qa: false,
  presence: false,
  jira: false,
  quiz: false,
  leave: false,
  employees: false,
  celebrations: false,
  members: false,
  engineering: false,
}

describe('settingsSections', () => {
  it('shows only pages the reader can open and drops empty groups', () => {
    const groups = settingsSections({ ...NONE, connections: true, engineering: true })
    expect(groups.map(g => g.label)).toEqual(['Workspace', 'Agents'])
    expect(groups[0].items.map(i => i.title)).toEqual(['Integrations'])
    expect(groups[1].items.map(i => i.to)).toEqual(['/settings/mcp-connect'])
  })
  it('lists everything for a reader with every permission', () => {
    const all = Object.fromEntries(Object.keys(NONE).map(k => [k, true])) as Record<SettingsPermission, boolean>
    expect(settingsSections(all).flatMap(g => g.items)).toHaveLength(14)
  })
})
