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
 * Chat-panel orchestration for the BUD detail page.
 *
 * Owns the chat-panel state (open flag, messages, loading, session id,
 * status line) and the round-trip with `budStore.chatBUD` + the job
 * tracker. The view stays a thin shell that wires the returned refs
 * into <ChatPanel> and emits events into the composable's methods.
 *
 * Cross-cutting side effects (editor write-through, design refresh,
 * tab switching) are injected as accessor/callback hooks so the
 * composable doesn't reach into view-only state directly.
 */

import { nextTick, ref } from 'vue'
import { useBUDStore } from '@/stores/bud'
import { useJobSocket } from '@/composables/useJobSocket'
import { friendlyAgentError } from '@/types/agentErrors'
import type { BUDDocument, BUDSectionKey } from '@/types'

export interface ChatMessage {
  role: 'user' | 'ai'
  text: string
  userName?: string | null
  images?: string[]
}

export interface BudChatHooks {
  /** Current BUD; null while the page is still loading. */
  getBud: () => BUDDocument | null
  /** Active section that chat messages target (drives history + send). */
  getCurrentSection: () => BUDSectionKey
  /** Active design tab id when the section is 'design'; undefined otherwise. */
  getDesignTabId: () => string | undefined
  /** Switch the page's active tab — used by enrichWithAI. */
  setActiveTab: (tab: string) => void
  /**
   * Mirror chat-returned `updated_content` into any open markdown editor
   * for non-design sections. The composable already writes the value
   * into `budStore.currentBUD` so the preview re-renders; this is for
   * the edit textarea that holds a separate ref.
   */
  syncEditor: (section: string, content: string) => void
  /** Design tab side effects when chat returns updated design content. */
  onDesignContentUpdated: () => void | Promise<void>
}

const JIRA_ENRICH_PROMPT
  = 'This BUD was imported from Jira with minimal description. '
  + 'DO NOT update the content yet. Instead, put your clarifying questions '
  + 'directly in the "reply" field and set "updated_content" to null. '
  + 'Ask me 2-3 questions about: what this feature does, who it\'s for, '
  + 'acceptance criteria, and edge cases. I will answer, then you write the PRD.'

export function useBudChat(hooks: BudChatHooks) {
  const budStore = useBUDStore()
  const { startTracking } = useJobSocket()

  const chatOpen = ref(false)
  const chatLoading = ref(false)
  const chatMessages = ref<ChatMessage[]>([])
  const chatStatusMessage = ref('')
  const currentSessionId = ref<string | undefined>(undefined)

  async function loadChatHistory(): Promise<void> {
    const bud = hooks.getBud()
    if (!bud) return
    const section = hooks.getCurrentSection()
    const designId = section === 'design' ? hooks.getDesignTabId() : undefined
    const history = await budStore.fetchChatHistory(
      bud.id, section, designId, currentSessionId.value,
    )
    chatMessages.value = history.map(m => ({
      role: m.role,
      text: m.message,
      userName: m.user_name,
    }))
  }

  function startNewSession(): void {
    currentSessionId.value = crypto.randomUUID()
    chatMessages.value = []
  }

  async function handleChatSend(msg: string, images: string[] = []): Promise<void> {
    const bud = hooks.getBud()
    if (!bud || chatLoading.value) return

    chatMessages.value.push({
      role: 'user',
      text: msg,
      images: images.length ? images : undefined,
    })
    chatLoading.value = true
    chatStatusMessage.value = ''

    const section = hooks.getCurrentSection()
    const designId = section === 'design' ? hooks.getDesignTabId() : undefined
    const result = await budStore.chatBUD(
      bud.id, msg, section, designId, currentSessionId.value, images,
    )
    if (!result) {
      chatMessages.value.push({
        role: 'ai',
        text: 'Sorry, something went wrong. Please try again.',
      })
      chatLoading.value = false
      return
    }

    // Persist the server-generated session_id so the next message in
    // this thread carries it forward — that's what lets the worker
    // pass --resume <id> and hit the Anthropic prompt cache on
    // iteration 2+.
    if (result.sessionId) currentSessionId.value = result.sessionId

    startTracking(result.jobId, {
      onProgress(status) {
        chatStatusMessage.value = status.statusMessage
      },
      async onComplete(data) {
        chatLoading.value = false
        const parsed = (data as unknown as Record<string, unknown>).result as
          { reply: string; updated_content: string | null } | null
        const reply = parsed?.reply || ''
        const updatedContent = parsed?.updated_content ?? null
        if (reply) chatMessages.value.push({ role: 'ai', text: reply })
        if (updatedContent !== null) {
          if (budStore.currentBUD) {
            (budStore.currentBUD as Record<string, unknown>)[section] = updatedContent
          }
          if (section === 'design') {
            await hooks.onDesignContentUpdated()
          } else {
            hooks.syncEditor(section, updatedContent)
          }
        }
        // Linked-features refetch is handled by the agentLocked watcher
        // (universal hook for any PM run, not just the chat-job path).
      },
      onError(err, errorCode) {
        chatLoading.value = false
        chatMessages.value.push({
          role: 'ai',
          text: friendlyAgentError(errorCode, err).headline,
        })
      },
    })
  }

  function enrichWithAI(): void {
    hooks.setActiveTab('requirements')
    chatOpen.value = true
    // Wait one flush so the tab switch lands before the seeded send —
    // otherwise the chat history fetch (triggered by the activeTab
    // watcher in the view) races with the user message push.
    void nextTick(() => {
      void handleChatSend(JIRA_ENRICH_PROMPT, [])
    })
  }

  return {
    chatOpen,
    chatLoading,
    chatMessages,
    chatStatusMessage,
    currentSessionId,
    loadChatHistory,
    startNewSession,
    handleChatSend,
    enrichWithAI,
  }
}
