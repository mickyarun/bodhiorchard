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
import { ref } from 'vue'
import type { AxiosError } from 'axios'
import api from '@/services/api'

export interface AgentSkill {
  skillSlug: string
  name: string
  description: string
  tools: string[]
  mcpTools: string[]
  prompt: string
  maxTurns: number
  model: string
  iterationModel: string
  effort: string
  isCustomized: boolean
}

interface AgentSkillApi {
  skill_slug: string
  name: string
  description: string
  tools: string[]
  mcp_tools: string[]
  prompt: string
  max_turns: number
  model: string
  iteration_model: string
  effort: string
  is_customized: boolean
}

function fromApi(raw: AgentSkillApi): AgentSkill {
  return {
    skillSlug: raw.skill_slug,
    name: raw.name,
    description: raw.description,
    tools: raw.tools,
    mcpTools: raw.mcp_tools,
    prompt: raw.prompt,
    maxTurns: raw.max_turns,
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

export const useAgentSkillsStore = defineStore('agentSkills', () => {
  const skills = ref<AgentSkill[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const saving = ref(false)
  const saveSuccess = ref(false)

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
    updates: Partial<Pick<AgentSkill, 'name' | 'description' | 'tools' | 'mcpTools' | 'prompt' | 'maxTurns' | 'model' | 'iterationModel' | 'effort'>>,
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
      if (updates.model !== undefined) payload.model = updates.model
      if (updates.iterationModel !== undefined) payload.iteration_model = updates.iterationModel
      if (updates.effort !== undefined) payload.effort = updates.effort

      const { data } = await api.put<AgentSkillApi>(`/v1/settings/agent-skills/${slug}`, payload)
      const updated = fromApi(data)
      const idx = skills.value.findIndex(s => s.skillSlug === slug)
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

  async function resetSkill(slug: string): Promise<boolean> {
    saving.value = true
    error.value = null
    try {
      await api.delete(`/v1/settings/agent-skills/${slug}`)
      await fetchSkills()
      return true
    } catch (err) {
      error.value = extractErrorMessage(err, 'Failed to reset skill.')
      return false
    } finally {
      saving.value = false
    }
  }

  return { skills, loading, error, saving, saveSuccess, fetchSkills, updateSkill, resetSkill }
})
