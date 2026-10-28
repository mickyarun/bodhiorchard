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

// The BUD detail page's tab state: which tabs exist, which is open, the
// section behind it, and whether that section can be edited or chatted
// about at the BUD's current stage.

import { computed, ref, watch, type ComputedRef } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import {
  BUD_SECTIONS,
  TAB_TO_SECTION,
  isSectionChatable,
  isSectionEditable,
  type BUDDocument,
  type BUDSectionKey,
} from '@/types'
import { READ_ONLY_TABS, STATUS_TAB_MAP, detailTabs } from '@/utils/budDetail'

// Stage that owns each section, for the "Move the BUD to X to edit"
// hint. Development has no editor; its tab hides the toolbar anyway.
const EDIT_LOCK_PHASE_LABEL: Record<BUDSectionKey, string | null> = {
  requirements_md: 'BUD',
  design: 'Design',
  tech_spec_md: 'Tech Architecture',
  testing: 'Testing',
  code_review: 'Code Review',
  development: null,
}

export function useBudDetailTabs(bud: ComputedRef<BUDDocument | null>) {
  const settingsStore = useSettingsStore()
  const activeTab = ref('requirements')

  // Org-level UAT toggle; assumed on while settings load so the tab
  // doesn't flicker in.
  const uatStageEnabled = computed(() => settingsStore.connections.budStages?.uatEnabled ?? true)
  const isClosed = computed(() => bud.value?.status === 'closed' || bud.value?.status === 'discarded')
  // The backend sets has_learning when there's a recap or metrics, or a
  // closed, opted-in BUD is still missing its recap (the recovery path).
  const hasLearning = computed(() => Boolean(bud.value?.has_learning))
  const tabs = computed(() =>
    bud.value
      ? detailTabs({ uatEnabled: uatStageEnabled.value, status: bud.value.status, hasLearning: hasLearning.value })
      : [],
  )
  const isReadOnlyTab = computed(() => READ_ONLY_TABS.has(activeTab.value))

  const currentSection = computed<BUDSectionKey>(() => TAB_TO_SECTION[activeTab.value] ?? 'requirements_md')
  const currentSectionLabel = computed(() => BUD_SECTIONS[currentSection.value].label)

  // A section is editable only while the BUD sits in the stage that owns
  // it; the backend enforces the same rule with a 409 (bud_edit_policy.py).
  const currentSectionEditable = computed(() => isSectionEditable(currentSection.value, bud.value?.status))
  const editLockTooltip = computed(() => {
    const required = EDIT_LOCK_PHASE_LABEL[currentSection.value]
    return required ? `Move the BUD to ${required} to edit this section` : 'This section is read-only'
  })

  // Chat follows the same stage gate. Design chat also needs a design row
  // to exist: otherwise the first message is stored without a design id
  // and the agent's new row strands it. The backend 409s that case too.
  const currentSectionChatable = computed(() => {
    if (!isSectionChatable(currentSection.value, bud.value?.status)) return false
    return currentSection.value !== 'design' || (bud.value?.designs ?? []).length > 0
  })
  // Chat is open on Design but nothing has been generated yet: the chat
  // panel shows "Generate a design first" instead of its input.
  const needsDesignGeneration = computed(
    () => currentSection.value === 'design' && (bud.value?.designs ?? []).length === 0,
  )

  // No UAT tab while the org has UAT off: fall back to Prod, whether UAT
  // was switched off with its tab open or the tab was asked for (a BUD
  // left in UAT opens on its stage tab; a ?tab=uat link).
  watch([uatStageEnabled, activeTab], ([enabled, tab]) => {
    if (!enabled && tab === 'uat') activeTab.value = 'prod'
  })
  // A status change on the open BUD opens the tab for the new stage. The
  // first load (and a switch to another BUD) is left to the loader, so a
  // ?tab= link keeps the tab it asked for.
  watch(
    () => [bud.value?.id, bud.value?.status] as const,
    ([id, status], [prevId, prevStatus]) => {
      if (!id || id !== prevId || !prevStatus || status === prevStatus) return
      if (status && STATUS_TAB_MAP[status]) activeTab.value = STATUS_TAB_MAP[status]
    },
  )

  return {
    activeTab,
    tabs,
    uatStageEnabled,
    isClosed,
    hasLearning,
    isReadOnlyTab,
    currentSection,
    currentSectionLabel,
    currentSectionEditable,
    currentSectionChatable,
    needsDesignGeneration,
    editLockTooltip,
  }
}
