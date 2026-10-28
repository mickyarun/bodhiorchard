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
import { defaultSkillCaps } from './skillCapabilities.util'
import { editFormFromSkill, emptyEditForm } from './skillEditForm.util'

describe('editFormFromSkill', () => {
  it('copies the editable fields and coerces model and effort to the provider', () => {
    const tools = ['Read']
    const skill = {
      id: '1', skillSlug: 's', agentType: 'bud', isDefault: false, isCustom: false,
      name: 'N', description: 'D', tools, mcpTools: ['m'], prompt: 'P', maxTurns: 3,
      timeoutSeconds: 60, model: 'sonnet', iterationModel: 'opus', iterationMaxTurns: 2,
      effort: 'high', isCustomized: false,
    } satisfies AgentSkill
    const form = editFormFromSkill(skill, defaultSkillCaps())
    expect(form).toEqual({
      ...emptyEditForm(),
      name: 'N', description: 'D', tools: ['Read'], mcpTools: ['m'], prompt: 'P',
      maxTurns: 3, timeoutSeconds: 60, iterationMaxTurns: 2,
    })
    expect(form.tools).not.toBe(tools)
  })
})
