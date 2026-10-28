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
import { AGENT_TYPE_ITEMS, canSubmit, slugError, templateForAgent } from './customSkillForm.util'

const seed = {
  id: '1', skillSlug: 'bud-writer', agentType: 'bud', isDefault: true, isCustom: false,
  name: 'BUD writer', description: 'Writes', tools: ['Read'], mcpTools: ['get_bud_context'],
  prompt: '# P', maxTurns: 5, timeoutSeconds: 0, model: 'opus', iterationModel: '',
  iterationMaxTurns: 0, effort: '', isCustomized: false,
} satisfies AgentSkill

describe('templateForAgent', () => {
  it('copies the seeded skill for the agent', () => {
    const form = templateForAgent([seed], 'bud')
    expect(form).toMatchObject({ skillSlug: 'bud-writer-copy', name: 'Copy of BUD writer', model: 'opus', maxTurns: 5 })
    expect(form.tools).not.toBe(seed.tools)
  })

  it('is blank when no seed is loaded for the agent', () => {
    expect(templateForAgent([{ ...seed, isCustom: true }], 'bud')).toMatchObject({ agentType: 'bud', skillSlug: '', prompt: '' })
  })
})

describe('validation', () => {
  it('flags a non-empty slug that is not lowercase-hyphenated', () => {
    expect(slugError('')).toBeNull()
    expect(slugError('my-pm')).toBeNull()
    expect(slugError('My PM')).toBe('Lowercase letters, digits, and hyphens only')
  })

  it('needs a name, a prompt and a valid slug', () => {
    const form = templateForAgent([seed], 'bud')
    expect(canSubmit(form)).toBe(true)
    expect(canSubmit({ ...form, name: '  ' })).toBe(false)
    expect(canSubmit({ ...form, skillSlug: '' })).toBe(false)
  })

  it('lists every agent type', () => {
    expect(AGENT_TYPE_ITEMS.find(i => i.value === 'bud')?.title).toBe('BUD (PRD writer)')
  })
})
