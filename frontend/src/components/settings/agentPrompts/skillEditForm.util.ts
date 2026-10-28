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

/** The editable fields of an agent skill, as the inline editor holds them. */

import type { AgentSkill, AgentType } from '@/stores/agentSkills'
import { coerceEffort, coerceModel, type SkillCaps } from './skillCapabilities.util'

export type PreviewMode = 'edit' | 'preview'

export const PREVIEW_MODE_OPTIONS: { label: string; value: PreviewMode }[] = [
  { label: 'Edit', value: 'edit' },
  { label: 'Preview', value: 'preview' },
]

export interface SkillEditForm {
  name: string
  description: string
  tools: string[]
  mcpTools: string[]
  prompt: string
  maxTurns: number
  timeoutSeconds: number
  model: string
  iterationModel: string
  iterationMaxTurns: number
  effort: string
}

/** A seeded skill the user asked to reset, as the confirm dialog shows it. */
export interface SkillResetTarget {
  slug: string
  agentType: AgentType
  isCustomized: boolean
}

export function emptyEditForm(): SkillEditForm {
  return {
    name: '',
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
  }
}

export function editFormFromSkill(skill: AgentSkill, caps: SkillCaps): SkillEditForm {
  return {
    name: skill.name,
    description: skill.description,
    tools: [...skill.tools],
    mcpTools: [...skill.mcpTools],
    prompt: skill.prompt,
    maxTurns: skill.maxTurns,
    timeoutSeconds: skill.timeoutSeconds ?? 0,
    // Preselect the active provider's model/effort — a foreign saved id
    // (e.g. Claude ``sonnet`` under a Codex org) coerces to the provider
    // default so the dropdown shows what actually runs, not a fallback label.
    model: coerceModel(caps, skill.model),
    iterationModel: coerceModel(caps, skill.iterationModel),
    iterationMaxTurns: skill.iterationMaxTurns ?? 0,
    effort: coerceEffort(caps, skill.effort),
  }
}
