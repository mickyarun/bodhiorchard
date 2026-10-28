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
 * The Agent Prompts page's single inline editor: which skill row is open,
 * its edit form and preview mode, and saving it. One form is shared by every
 * row, so only one skill is edited at a time.
 */
import { ref, type Ref } from 'vue'
import { useAgentSkillsStore, type AgentSkill } from '@/stores/agentSkills'
import { skillKey } from '@/components/settings/agentPrompts/agentPrompts.util'
import type { SkillCaps } from '@/components/settings/agentPrompts/skillCapabilities.util'
import {
  editFormFromSkill,
  emptyEditForm,
  type PreviewMode,
  type SkillEditForm,
} from '@/components/settings/agentPrompts/skillEditForm.util'

export function useAgentSkillEditor(caps: Ref<SkillCaps>) {
  const store = useAgentSkillsStore()
  const expanded = ref<string | null>(null)
  const previewMode = ref<PreviewMode>('edit')
  const editForm = ref<SkillEditForm>(emptyEditForm())

  function isOpen(skill: AgentSkill): boolean {
    return expanded.value === skillKey(skill)
  }

  function toggle(skill: AgentSkill): void {
    const key = skillKey(skill)
    if (expanded.value === key) {
      expanded.value = null
      return
    }
    expanded.value = key
    previewMode.value = 'edit'
    editForm.value = editFormFromSkill(skill, caps.value)
  }

  function collapse(): void {
    expanded.value = null
  }

  async function saveSkill(skill: AgentSkill): Promise<void> {
    await store.updateSkill(skill.skillSlug, skill.agentType, { ...editForm.value })
  }

  return { expanded, previewMode, editForm, isOpen, toggle, collapse, saveSkill }
}
