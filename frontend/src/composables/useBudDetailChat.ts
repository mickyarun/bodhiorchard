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

// The BUD detail page's AI chat: the useBudChat thread scoped to the open
// section, the chat's design picker, and the rules for when the panel
// closes by itself.

import { computed, watch, type ComputedRef, type Ref } from 'vue'
import { useBudChat } from '@/composables/useBudChat'
import type { BUDDocument, BUDSectionKey } from '@/types'

export interface ChatDesignPanel {
  activeDesignTab?: string | null
  loadDesigns: () => Promise<void> | void
  refreshDesignPreview: () => void
  triggerDesignGeneration: () => Promise<void> | void
}

export interface BudDetailChatOptions {
  bud: ComputedRef<BUDDocument | null>
  activeTab: Ref<string>
  currentSection: ComputedRef<BUDSectionKey>
  chatable: ComputedRef<boolean>
  agentLocked: ComputedRef<boolean>
  getDesignPanel: () => ChatDesignPanel | null
  syncEditor: (section: string, content: string) => void
}

export function useBudDetailChat(o: BudDetailChatOptions) {
  const chat = useBudChat({
    getBud: () => o.bud.value,
    getCurrentSection: () => o.currentSection.value,
    getDesignTabId: () => o.getDesignPanel()?.activeDesignTab ?? undefined,
    setActiveTab: (tab) => { o.activeTab.value = tab },
    syncEditor: o.syncEditor,
    onDesignContentUpdated: async () => {
      if (o.bud.value) await o.getDesignPanel()?.loadDesigns()
      o.getDesignPanel()?.refreshDesignPreview()
    },
  })
  const { chatOpen, chatLoading, currentSessionId, loadChatHistory } = chat

  // The design picker shows only on Design; ChatPanel shows it from two designs up.
  const chatDesignOptions = computed(() =>
    o.currentSection.value === 'design'
      ? (o.bud.value?.designs ?? []).map(d => ({ id: d.id, repoName: d.repo_name }))
      : [],
  )

  // Tech spec's empty state: open the chat on Tech spec so the AI drafts it.
  function openTechSpecChat(): void {
    o.activeTab.value = 'tech-spec'
    chatOpen.value = true
  }

  // From the chat's "Generate a design first": show Design, then start generating.
  function openGenerateDesigns(): void {
    o.activeTab.value = 'design'
    void o.getDesignPanel()?.triggerDesignGeneration()
  }

  // Close when the section stops being chattable at this stage.
  watch(o.chatable, (chatable) => {
    if (!chatable && chatOpen.value) chatOpen.value = false
  })
  // An agent started from elsewhere closes the chat; one the chat itself
  // started (chatLoading) leaves it open.
  watch(o.agentLocked, (locked) => {
    if (locked && !chatLoading.value && chatOpen.value) chatOpen.value = false
  })
  // Each section has its own thread.
  watch(o.activeTab, () => {
    currentSessionId.value = undefined
    void loadChatHistory()
  })

  return { ...chat, chatDesignOptions, openTechSpecChat, openGenerateDesigns }
}
