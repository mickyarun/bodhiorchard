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

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { AxiosError } from 'axios'
import api from '@/services/api'

// Mirrors the Python AgentType enum. Frozen string literals keep the
// TS-side type-check honest if a new agent type lands in the backend.
export type AgentType =
  | 'triage'
  | 'bud'
  | 'status'
  | 'standup'
  | 'learning'
  | 'bugLinker'
  | 'reassignment'
  | 'skill'
  | 'techPlan'
  | 'testPlan'
  | 'design'
  | 'slackTriage'

export const AGENT_TYPE_LABELS: Record<AgentType, string> = {
  triage: 'Triage',
  bud: 'BUD (PRD writer)',
  status: 'Status / DevOps',
  standup: 'Standup digest',
  learning: 'Learning recap',
  bugLinker: 'Bug linker',
  reassignment: 'Reassignment',
  skill: 'Skill / code review',
  techPlan: 'Tech plan',
  testPlan: 'Test plan',
  design: 'Design',
  slackTriage: 'Slack triage',
}

export interface AgentSkill {
  id: string | null
  skillSlug: string
  agentType: AgentType
  isDefault: boolean
  isCustom: boolean
  name: string
  description: string
  tools: string[]
  mcpTools: string[]
  prompt: string
  maxTurns: number
  timeoutSeconds: number
  model: string
  iterationModel: string
  effort: string
  isCustomized: boolean
}

interface AgentSkillApi {
  id: string | null
  skill_slug: string
  agent_type: AgentType
  is_default: boolean
  is_custom: boolean
  name: string
  description: string
  tools: string[]
  mcp_tools: string[]
  prompt: string
  max_turns: number
  timeout_seconds: number
  model: string
  iteration_model: string
  effort: string
  is_customized: boolean
}

function fromApi(raw: AgentSkillApi): AgentSkill {
  return {
    id: raw.id ?? null,
    skillSlug: raw.skill_slug,
    agentType: raw.agent_type,
    isDefault: raw.is_default,
    isCustom: raw.is_custom,
    name: raw.name,
    description: raw.description,
    tools: raw.tools,
    mcpTools: raw.mcp_tools,
    prompt: raw.prompt,
    maxTurns: raw.max_turns,
    timeoutSeconds: raw.timeout_seconds ?? 0,
    model: raw.model ?? '',
    iterationModel: raw.iteration_model ?? '',
    effort: raw.effort ?? '',
    isCustomized: raw.is_customized,
  }
}

function extractErrorMessage(err: unknown, fallback: string): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const axiosErr = err as AxiosError<{ detail?: string }>
    if (axiosErr.response?.data?.detail) return axiosErr.response.data.detail
    if (axiosErr.response?.status === 403) return 'You do not have permission for this action.'
  }
  return fallback
}

export interface CustomSkillCreatePayload {
  skillSlug: string
  agentType: AgentType
  name: string
  description?: string
  prompt: string
  tools?: string[]
  mcpTools?: string[]
  maxTurns?: number
  timeoutSeconds?: number
  model?: string
  iterationModel?: string
  effort?: string
}

export const useAgentSkillsStore = defineStore('agentSkills', () => {
  const skills = ref<AgentSkill[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const saving = ref(false)
  const saveSuccess = ref(false)

  // Group view used by the new settings UI — keyed by AgentType, each
  // entry sorted seeded-first then custom alphabetical.
  const byAgentType = computed<Record<string, AgentSkill[]>>(() => {
    const grouped: Record<string, AgentSkill[]> = {}
    for (const s of skills.value) {
      const list = grouped[s.agentType] ?? (grouped[s.agentType] = [])
      list.push(s)
    }
    for (const list of Object.values(grouped)) {
      list.sort((a, b) => {
        if (a.isCustom !== b.isCustom) return a.isCustom ? 1 : -1
        return a.name.localeCompare(b.name)
      })
    }
    return grouped
  })

  async function fetchSkills(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get<AgentSkillApi[]>('/v1/settings/agent-skills/')
      skills.value = data.map(fromApi)
    } catch (err) {
      error.value = extractErrorMessage(err, 'Failed to load agent skills.')
    } finally {
      loading.value = false
    }
  }

  async function updateSkill(
    slug: string,
    agentType: AgentType,
    updates: Partial<
      Pick<
        AgentSkill,
        | 'name'
        | 'description'
        | 'tools'
        | 'mcpTools'
        | 'prompt'
        | 'maxTurns'
        | 'timeoutSeconds'
        | 'model'
        | 'iterationModel'
        | 'effort'
      >
    >,
  ): Promise<boolean> {
    saving.value = true
    error.value = null
    saveSuccess.value = false
    try {
      const payload: Record<string, unknown> = {}
      if (updates.name !== undefined) payload.name = updates.name
      if (updates.description !== undefined) payload.description = updates.description
      if (updates.tools !== undefined) payload.tools = updates.tools
      if (updates.mcpTools !== undefined) payload.mcp_tools = updates.mcpTools
      if (updates.prompt !== undefined) payload.prompt = updates.prompt
      if (updates.maxTurns !== undefined) payload.max_turns = updates.maxTurns
      if (updates.timeoutSeconds !== undefined) payload.timeout_seconds = updates.timeoutSeconds
      if (updates.model !== undefined) payload.model = updates.model
      if (updates.iterationModel !== undefined) payload.iteration_model = updates.iterationModel
      if (updates.effort !== undefined) payload.effort = updates.effort

      const { data } = await api.put<AgentSkillApi>(
        `/v1/settings/agent-skills/${slug}`,
        payload,
        { params: { agent_type: agentType } },
      )
      const updated = fromApi(data)
      const idx = skills.value.findIndex(
        s => s.skillSlug === slug && s.agentType === agentType,
      )
      if (idx >= 0) skills.value[idx] = updated
      saveSuccess.value = true
      return true
    } catch (err) {
      error.value = extractErrorMessage(err, 'Failed to save skill.')
      return false
    } finally {
      saving.value = false
    }
  }

  async function resetSkill(slug: string, agentType: AgentType): Promise<boolean> {
    saving.value = true
    error.value = null
    try {
      await api.delete(`/v1/settings/agent-skills/${slug}`, { params: { agent_type: agentType } })
      await fetchSkills()
      return true
    } catch (err) {
      error.value = extractErrorMessage(err, 'Failed to reset skill.')
      return false
    } finally {
      saving.value = false
    }
  }

  async function createCustomSkill(payload: CustomSkillCreatePayload): Promise<AgentSkill | null> {
    saving.value = true
    error.value = null
    try {
      const body = {
        skill_slug: payload.skillSlug,
        agent_type: payload.agentType,
        name: payload.name,
        description: payload.description ?? '',
        prompt: payload.prompt,
        tools: payload.tools ?? [],
        mcp_tools: payload.mcpTools ?? [],
        max_turns: payload.maxTurns ?? 0,
        timeout_seconds: payload.timeoutSeconds ?? 0,
        model: payload.model ?? '',
        iteration_model: payload.iterationModel ?? '',
        effort: payload.effort ?? '',
      }
      const { data } = await api.post<AgentSkillApi>('/v1/settings/agent-skills/', body)
      const created = fromApi(data)
      skills.value.push(created)
      saveSuccess.value = true
      return created
    } catch (err) {
      error.value = extractErrorMessage(err, 'Failed to create custom skill.')
      return null
    } finally {
      saving.value = false
    }
  }

  async function setDefault(skillId: string): Promise<boolean> {
    saving.value = true
    error.value = null
    try {
      const { data } = await api.post<AgentSkillApi>(
        `/v1/settings/agent-skills/${skillId}/set-default`,
      )
      const updated = fromApi(data)
      // Demote any other default in the same agent_type locally, then upsert.
      for (const s of skills.value) {
        if (s.agentType === updated.agentType && s.id !== updated.id) s.isDefault = false
      }
      const idx = skills.value.findIndex(s => s.id === updated.id)
      if (idx >= 0) skills.value[idx] = updated
      saveSuccess.value = true
      return true
    } catch (err) {
      error.value = extractErrorMessage(err, 'Failed to set default skill.')
      return false
    } finally {
      saving.value = false
    }
  }

  async function deleteCustomSkill(skillId: string): Promise<boolean> {
    saving.value = true
    error.value = null
    try {
      await api.delete(`/v1/settings/agent-skills/by-id/${skillId}`)
      skills.value = skills.value.filter(s => s.id !== skillId)
      return true
    } catch (err) {
      error.value = extractErrorMessage(err, 'Failed to delete custom skill.')
      return false
    } finally {
      saving.value = false
    }
  }

  return {
    skills,
    byAgentType,
    loading,
    error,
    saving,
    saveSuccess,
    fetchSkills,
    updateSkill,
    resetSkill,
    createCustomSkill,
    setDefault,
    deleteCustomSkill,
  }
})
