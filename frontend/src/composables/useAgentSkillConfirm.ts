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
 * The Agent Prompts page's reset and delete confirmations. A dialog is open
 * while its target is set; confirming runs the store action and, when it
 * succeeds, calls ``onDone`` (the page collapses the open editor).
 */
import { computed, ref } from 'vue'
import { useAgentSkillsStore } from '@/stores/agentSkills'
import type { SkillResetTarget } from '@/components/settings/agentPrompts/skillEditForm.util'

export function useAgentSkillConfirm(onDone: () => void) {
  const store = useAgentSkillsStore()
  const confirmResetTarget = ref<SkillResetTarget | null>(null)
  const confirmDeleteId = ref<string | null>(null)

  const showResetDialog = computed({
    get: () => confirmResetTarget.value !== null,
    set: (v: boolean) => { if (!v) confirmResetTarget.value = null },
  })

  const showDeleteDialog = computed({
    get: () => confirmDeleteId.value !== null,
    set: (v: boolean) => { if (!v) confirmDeleteId.value = null },
  })

  async function doReset(): Promise<void> {
    const target = confirmResetTarget.value
    if (!target) return
    const ok = await store.resetSkill(target.slug, target.agentType)
    confirmResetTarget.value = null
    if (ok) onDone()
  }

  async function doDelete(): Promise<void> {
    const id = confirmDeleteId.value
    if (!id) return
    const ok = await store.deleteCustomSkill(id)
    confirmDeleteId.value = null
    if (ok) onDone()
  }

  return {
    confirmResetTarget, confirmDeleteId, showResetDialog, showDeleteDialog, doReset, doDelete,
  }
}
