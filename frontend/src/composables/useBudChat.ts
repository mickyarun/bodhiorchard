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
 * Owns the chat-panel state and the round-trip with `budStore.chatBUD`
 * + the job tracker. Three peer modules own narrower responsibilities:
 *
 *   - ``useChatRetry`` — single-attempt auto-retry budget + banner.
 *   - ``useChatHistoryLoader`` — AbortController-backed history fetch.
 *   - ``chatJobSocket`` — job-socket callback bag (onComplete/onError).
 */

import { nextTick, ref } from 'vue'
import { useBUDStore } from '@/stores/bud'
import { useJobSocket } from '@/composables/useJobSocket'
import { useChatRetry } from '@/composables/useChatRetry'
import { useChatHistoryLoader } from '@/composables/useChatHistoryLoader'
import { JIRA_ENRICH_PROMPT } from '@/composables/jiraEnrichPrompt'
import { makeChatSocketCallbacks } from '@/composables/chatJobSocket'
import type { BUDDocument, BUDSectionKey } from '@/types'

export interface ChatMessage {
  role: 'user' | 'ai'
  text: string
  userName?: string | null
  images?: string[]
}

export interface BudChatHooks {
  getBud: () => BUDDocument | null
  getCurrentSection: () => BUDSectionKey
  getDesignTabId: () => string | undefined
  setActiveTab: (tab: string) => void
  syncEditor: (section: string, content: string) => void
  onDesignContentUpdated: () => void | Promise<void>
}

export function useBudChat(hooks: BudChatHooks) {
  const budStore = useBUDStore()
  const { startTracking } = useJobSocket()

  const chatOpen = ref(false)
  const chatLoading = ref(false)
  const chatMessages = ref<ChatMessage[]>([])
  const chatStatusMessage = ref('')
  const currentSessionId = ref<string | undefined>(undefined)
  const stageGateMessage = ref('')

  const history = useChatHistoryLoader({
    getBudId: () => hooks.getBud()?.id ?? null,
    getScope: () => {
      const section = hooks.getCurrentSection()
      return {
        section,
        designId: section === 'design' ? hooks.getDesignTabId() : undefined,
      }
    },
    getSessionId: () => currentSessionId.value,
    fetch: (budId, section, designId, sessionId, signal) =>
      budStore.fetchChatHistory(budId, section, designId, sessionId, signal),
  })

  const retry = useChatRetry({
    resend: (msg, images) => sendOnce(msg, images),
    setStatus: (text) => { chatStatusMessage.value = text },
    setLoading: (loading) => { chatLoading.value = loading },
  })

  async function loadChatHistory(): Promise<void> {
    const loaded = await history.load()
    if (loaded === null) return
    chatMessages.value = loaded.map(m => ({
      role: m.role,
      text: m.message,
      userName: m.user_name,
    }))
  }

  function startNewSession(): void {
    // Server owns the session id; undefined ⇒ next send is a fresh
    // claim. Worker mints + echoes the new id via ``result.session_id``.
    currentSessionId.value = undefined
    chatMessages.value = []
    retry.resetBudget()
    retry.lastUserMessage.value = null
    stageGateMessage.value = ''
  }

  async function applyUpdatedContent(
    section: BUDSectionKey,
    content: string,
  ): Promise<void> {
    if (budStore.currentBUD) {
      (budStore.currentBUD as Record<string, unknown>)[section] = content
    }
    if (section === 'design') {
      await hooks.onDesignContentUpdated()
    } else {
      hooks.syncEditor(section, content)
    }
  }

  async function sendOnce(msg: string, images: string[]): Promise<boolean> {
    // Cancel any stale history fetch so it cannot clobber the push.
    history.abortInflight()
    const bud = hooks.getBud()
    if (!bud) return false

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
      return false
    }
    if ('stageGateError' in result) {
      // 409: surface banner and roll back the optimistic user push.
      stageGateMessage.value = result.stageGateError
      const last = chatMessages.value[chatMessages.value.length - 1]
      if (last && last.role === 'user') chatMessages.value.pop()
      chatLoading.value = false
      return false
    }

    if (result.sessionId) currentSessionId.value = result.sessionId
    startTracking(result.jobId, makeChatSocketCallbacks(section, {
      pushMessage: (m) => chatMessages.value.push(m),
      setStatus: (text) => { chatStatusMessage.value = text },
      setLoading: (loading) => { chatLoading.value = loading },
      setSessionId: (id) => { currentSessionId.value = id },
      applyUpdatedContent,
      maybeAutoRetry: () => retry.maybeAutoRetry(),
    }))
    return true
  }

  async function handleChatSend(msg: string, images: string[] = []): Promise<void> {
    const bud = hooks.getBud()
    if (!bud || chatLoading.value) return
    stageGateMessage.value = ''
    retry.resetBudget()
    retry.rememberTurn(msg, images)

    chatMessages.value.push({
      role: 'user',
      text: msg,
      images: images.length ? images : undefined,
    })
    chatLoading.value = true
    chatStatusMessage.value = ''

    await sendOnce(msg, images)
  }

  function enrichWithAI(): void {
    hooks.setActiveTab('requirements')
    chatOpen.value = true
    // Defer one tick so the tab switch lands before the seeded send —
    // otherwise the chat history fetch (activeTab watcher in the view)
    // races with the user push.
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
    stageGateMessage,
    retryPrompt: retry.retryPrompt,
    loadChatHistory,
    startNewSession,
    handleChatSend,
    manualRetry: retry.manualRetry,
    enrichWithAI,
  }
}
