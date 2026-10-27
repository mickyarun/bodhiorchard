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

import { computed, ref, watch, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAgentSkillsStore, type AgentSkill, type AgentType } from '@/stores/agentSkills'
import { useBUDStore } from '@/stores/bud'
import type { BUDPriority, BUDStatus } from '@/types'

/** A stage whose agent can be switched on and given a skill at creation. */
export interface CreateStage {
  value: BUDStatus
  label: string
  agentType: AgentType
}

export interface StageSkillOption {
  id: string
  label: string
}

// Mirrors BUD_STAGE_AGENT_TYPE in backend/app/agents/skill_mapping.py. If a
// new stage gets an agent on the backend, add it here too.
export const CREATE_STAGES: readonly CreateStage[] = [
  { value: 'bud', label: 'PRD writer', agentType: 'bud' },
  { value: 'design', label: 'Design', agentType: 'design' },
  { value: 'tech_arch', label: 'Tech plan', agentType: 'techPlan' },
  { value: 'testing', label: 'Test plan', agentType: 'testPlan' },
  { value: 'closed', label: 'Learning recap', agentType: 'learning' },
]

/**
 * State and submit logic for the New BUD form. Every stage's agent starts
 * on (the learning recap included: it feeds the estimator), and each stage
 * is pre-filled with that agent's current default skill so the form shows
 * what would run if nothing changes.
 */
export function useBudCreateForm(open: Ref<boolean>) {
  const router = useRouter()
  const budStore = useBUDStore()
  const skillsStore = useAgentSkillsStore()

  const title = ref('')
  const description = ref('')
  const priority = ref<BUDPriority>('P2')
  const creating = ref(false)
  const error = ref('')
  /** Which expansion panels are open; empty means Advanced is closed. */
  const openPanels = ref<string[]>([])
  const stageSkillPicks = ref<Record<string, string | null>>({})
  const autoGenerate = ref<Record<string, boolean>>({})
  const skillsLoading = computed(() => skillsStore.loading)

  function skillsForStage(agentType: AgentType): StageSkillOption[] {
    return skillsStore.skills
      .filter((s): s is AgentSkill & { id: string } => s.agentType === agentType && s.id !== null)
      .map(s => ({ id: s.id, label: s.isDefault ? `${s.name} · default` : s.name }))
  }

  function defaultSkillId(agentType: AgentType): string | null {
    return skillsStore.skills.find(s => s.agentType === agentType && s.isDefault)?.id ?? null
  }

  function prefillDefaults(): void {
    for (const stage of CREATE_STAGES) {
      stageSkillPicks.value[stage.value] = defaultSkillId(stage.agentType)
      if (autoGenerate.value[stage.value] === undefined) autoGenerate.value[stage.value] = true
    }
  }

  function reset(): void {
    title.value = ''
    description.value = ''
    priority.value = 'P2'
    stageSkillPicks.value = {}
    autoGenerate.value = {}
    openPanels.value = []
  }

  watch(open, async isOpen => {
    if (!isOpen) return
    if (skillsStore.skills.length === 0 && !skillsStore.loading) await skillsStore.fetchSkills()
    prefillDefaults()
  })

  // Skills that land after the dialog opened (slow network) still prefill.
  watch(() => skillsStore.skills.length, () => {
    if (open.value) prefillDefaults()
  })

  async function submit(): Promise<void> {
    if (!title.value.trim() || creating.value) return
    creating.value = true
    error.value = ''
    // Only non-default picks are stored, so the BUD keeps following whatever
    // the org marks as default later instead of pinning today's skill.
    const overrides: Record<string, string> = {}
    const phases: Record<string, boolean> = {}
    for (const stage of CREATE_STAGES) {
      const picked = stageSkillPicks.value[stage.value]
      if (picked && picked !== defaultSkillId(stage.agentType)) overrides[stage.value] = picked
      phases[stage.value] = !!autoGenerate.value[stage.value]
    }
    const bud = await budStore.createBUD(
      title.value.trim(),
      description.value.trim() || undefined,
      Object.keys(overrides).length > 0 ? overrides : undefined,
      phases,
      priority.value,
    )
    creating.value = false
    if (!bud) {
      error.value = budStore.error || "Couldn't create the BUD. Try again."
      return
    }
    open.value = false
    reset()
    void router.push(`/buds/${bud.id}`)
  }

  return {
    title,
    description,
    priority,
    creating,
    error,
    openPanels,
    stageSkillPicks,
    autoGenerate,
    skillsLoading,
    skillsForStage,
    submit,
  }
}
