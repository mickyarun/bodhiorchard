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
import type { AgentSkill } from '@/stores/agentSkills'
import { agentBlurb, agentIcon, agentTypeLabel, groupAgentSkills, skillKey } from './agentPrompts.util'

function skill(overrides: Partial<AgentSkill>): AgentSkill {
  return {
    id: null,
    skillSlug: 'slug',
    agentType: 'bud',
    isDefault: false,
    isCustom: false,
    name: 'Skill',
    description: '',
    tools: [],
    mcpTools: [],
    prompt: '',
    maxTurns: 0,
    timeoutSeconds: 0,
    model: '',
    iterationModel: '',
    iterationMaxTurns: 0,
    effort: '',
    isCustomized: false,
    ...overrides,
  }
}

describe('agent identity', () => {
  it('keys a skill by slug and agent type', () => {
    expect(skillKey(skill({ skillSlug: 'pm', agentType: 'design' }))).toBe('pm__design')
  })

  it('labels, icons and blurbs each agent type', () => {
    expect(agentTypeLabel('techPlan')).toBe('Tech plan')
    expect(agentIcon('slackTriage')).toBe('mdi-slack')
    expect(agentBlurb('bud')).toBe('Writes the PRD when a BUD is opened')
  })
})

describe('groupAgentSkills', () => {
  const skills = [
    skill({ name: 'Zed', agentType: 'triage' }),
    skill({ name: 'Custom one', agentType: 'bud', isCustom: true }),
    skill({ name: 'Beta', agentType: 'bud', isCustomized: true }),
    skill({ name: 'Alpha', agentType: 'bud' }),
    skill({ name: 'Default', agentType: 'bud', isDefault: true }),
  ]

  it('orders groups by lifecycle and skills seeded, default first, then by name', () => {
    const groups = groupAgentSkills(skills, 'all', '')
    expect(groups.map(g => g.agentType)).toEqual(['bud', 'triage'])
    expect(groups[0].skills.map(s => s.name)).toEqual(['Default', 'Alpha', 'Beta', 'Custom one'])
  })

  it('filters to custom or modified skills', () => {
    expect(groupAgentSkills(skills, 'custom', '')[0].skills.map(s => s.name)).toEqual(['Custom one'])
    expect(groupAgentSkills(skills, 'modified', '')[0].skills.map(s => s.name)).toEqual(['Beta'])
  })

  it('searches name, description and slug, ignoring case and padding', () => {
    const found = groupAgentSkills([...skills, skill({ skillSlug: 'needle-x', agentType: 'design' })], 'all', '  NEEDLE ')
    expect(found).toHaveLength(1)
    expect(found[0].agentType).toBe('design')
  })

  it('returns no groups when nothing matches', () => {
    expect(groupAgentSkills(skills, 'all', 'nothing-here')).toEqual([])
  })
})
