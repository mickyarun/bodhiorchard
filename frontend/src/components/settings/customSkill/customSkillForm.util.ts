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

/** Form state, options and validation for the "New custom skill" dialog. */

import { AGENT_TYPE_LABELS, type AgentSkill, type AgentType } from '@/stores/agentSkills'

export interface CustomSkillForm {
  agentType: AgentType
  skillSlug: string
  name: string
  description: string
  prompt: string
  tools: string[]
  mcpTools: string[]
  model: string
  maxTurns: number
}

export const CUSTOM_SKILL_MODEL_OPTIONS = [
  { title: 'Default', value: '' },
  { title: 'Sonnet', value: 'sonnet' },
  { title: 'Opus', value: 'opus' },
  { title: 'Haiku', value: 'haiku' },
]

const SLUG_REGEX = /^[a-z0-9][a-z0-9-]*$/

export const AGENT_TYPE_ITEMS: { value: AgentType; title: string }[] =
  (Object.keys(AGENT_TYPE_LABELS) as AgentType[]).map(value => ({
    value,
    title: AGENT_TYPE_LABELS[value],
  }))

// Pre-fill the form from the seeded skill for ``agentType``. Gives the
// user a working starting point so creating a custom skill is "edit the
// template", not "find every tool name from memory". When no seed has
// been loaded yet (store still fetching), returns a blank form.
export function templateForAgent(skills: AgentSkill[], agentType: AgentType): CustomSkillForm {
  const seed = skills.find(s => s.agentType === agentType && !s.isCustom)
  if (!seed) {
    return {
      agentType,
      skillSlug: '',
      name: '',
      description: '',
      prompt: '',
      tools: [],
      mcpTools: [],
      model: '',
      maxTurns: 0,
    }
  }
  return {
    agentType,
    skillSlug: `${seed.skillSlug}-copy`,
    name: `Copy of ${seed.name}`,
    description: seed.description,
    prompt: seed.prompt,
    tools: [...seed.tools],
    mcpTools: [...seed.mcpTools],
    model: seed.model,
    maxTurns: seed.maxTurns,
  }
}

export function slugError(slug: string): string | null {
  if (slug === '') return null
  return SLUG_REGEX.test(slug)
    ? null
    : 'Lowercase letters, digits, and hyphens only'
}

export function canSubmit(form: CustomSkillForm): boolean {
  return (
    form.name.trim().length > 0 &&
    form.prompt.trim().length > 0 &&
    SLUG_REGEX.test(form.skillSlug)
  )
}
