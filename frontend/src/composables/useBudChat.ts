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
import type { Ref } from 'vue'
import { useBUDStore } from '@/stores/bud'
import { useJobSocket } from '@/composables/useJobSocket'
import { useChatRetry } from '@/composables/useChatRetry'
import { useChatHistoryLoader } from '@/composables/useChatHistoryLoader'
import { JIRA_ENRICH_PROMPT } from '@/composables/jiraEnrichPrompt'
import { makeChatSocketCallbacks } from '@/composables/chatJobSocket'
import { makeResumeActiveChat } from '@/composables/chatResume'
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
  // Hard stage-gate banner: BUD is in the wrong status for this section.
  // Gates the textarea so the user can't push more messages until they
  // advance the BUD or switch sections.
  const stageGateMessage = ref('')
  // Soft banner: another client is already chatting in this section.
  // Informational only — the resumed job's terminal frame clears it
  // (via the wrapped setLoading hook) so the user can chat again.
  const chatInProgressBanner = ref('')

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

  const retry = useChatRetry({
    resend: (msg, images) => sendOnce(msg, images),
    setStatus: (text) => { chatStatusMessage.value = text },
    setLoading: (loading) => { chatLoading.value = loading },
  })

  // ``setLoading`` wrapper used by every job-socket subscription. When
  // loading flips from true→false the watched chat has terminated, so
  // also clear the soft "another chat is running" banner — without
  // this the banner would linger past the watched job's end.
  function setChatLoading(loading: boolean): void {
    chatLoading.value = loading
    if (!loading) chatInProgressBanner.value = ''
  }

  // Shared socket-callback bag — both the originate (``sendOnce``) and
  // resume-on-remount paths feed this to ``makeChatSocketCallbacks`` so
  // their terminal-frame handling is identical.
  const socketCallbacks = {
    pushMessage: (m: ChatMessage) => chatMessages.value.push(m),
    setStatus: (text: string) => { chatStatusMessage.value = text },
    setLoading: setChatLoading,
    setSessionId: (id: string) => { currentSessionId.value = id },
    applyUpdatedContent,
    maybeAutoRetry: () => retry.maybeAutoRetry(),
  }

  const resumeActiveChat = makeResumeActiveChat({
    getBud: () => {
      const bud = hooks.getBud()
      return bud ? { id: bud.id } : null
    },
    getCurrentSection: hooks.getCurrentSection,
    getDesignTabId: hooks.getDesignTabId,
    fetchActiveChatJob: (budId, section, designId) =>
      budStore.fetchActiveChatJob(budId, section, designId),
    startTracking,
    setLoading: setChatLoading,
    setStatus: (text) => { chatStatusMessage.value = text },
    socketCallbacks,
  })

  /** Roll back the optimistic user push and surface a 409 banner.
   *
   * Target ref differs by 409 flavour: stage-gate locks the input via
   * ``stageGateMessage``; chat-in-progress uses the softer
   * ``chatInProgressBanner`` that does NOT gate input — when the
   * watched chat ends, ``setChatLoading`` clears it and the user can
   * resume sending.
   */
  function rollbackOptimisticUserPush(target: Ref<string>, banner: string): void {
    target.value = banner
    const last = chatMessages.value[chatMessages.value.length - 1]
    if (last && last.role === 'user') chatMessages.value.pop()
    chatLoading.value = false
  }

  async function loadChatHistory(): Promise<void> {
    const loaded = await history.load()
    if (loaded === null) return
    chatMessages.value = loaded.map(m => ({
      role: m.role,
      text: m.message,
      userName: m.user_name,
    }))
    await resumeActiveChat()
  }

  function startNewSession(): void {
    // Server owns the session id; undefined ⇒ next send is a fresh
    // claim. Worker mints + echoes the new id via ``result.session_id``.
    currentSessionId.value = undefined
    chatMessages.value = []
    retry.resetBudget()
    retry.lastUserMessage.value = null
    stageGateMessage.value = ''
    chatInProgressBanner.value = ''
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
      rollbackOptimisticUserPush(stageGateMessage, result.stageGateError)
      return false
    }
    if ('permissionError' in result) {
      // 403: RBAC rejected the user. Surface the server's reason in the
      // hard-lock banner so the input stays disabled — no point letting
      // them keep typing when every send will be rejected.
      rollbackOptimisticUserPush(stageGateMessage, result.permissionError)
      return false
    }
    if ('chatInProgressError' in result) {
      // Another client (or tab) holds the section's active-job claim.
      // Subscribe to the winning job so the user sees its live progress
      // in their panel instead of an empty thread.
      rollbackOptimisticUserPush(
        chatInProgressBanner,
        'Another chat is already running for this section. Showing its progress.',
      )
      void resumeActiveChat()
      return false
    }

    if (result.sessionId) currentSessionId.value = result.sessionId
    startTracking(result.jobId, makeChatSocketCallbacks(section, socketCallbacks))
    return true
  }

  async function handleChatCancel(): Promise<void> {
    const bud = hooks.getBud()
    if (!bud || !chatLoading.value) return
    const section = hooks.getCurrentSection()
    const designId = section === 'design' ? hooks.getDesignTabId() : undefined
    // Fire-and-forget — the worker's CancelledError branch publishes
    // the terminal WS frame, which flips chatLoading=false through the
    // shared socketCallbacks. If the POST itself fails (404 / 500 /
    // network), swallow it: the spinner is left to time out naturally
    // because the job may still be alive on the server, and we don't
    // want a Vue click-handler unhandled-rejection warning.
    try {
      await budStore.cancelActiveChat(bud.id, section, designId)
    } catch {
      // intentional no-op — see comment above
    }
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
    chatInProgressBanner,
    retryPrompt: retry.retryPrompt,
    loadChatHistory,
    startNewSession,
    handleChatSend,
    handleChatCancel,
    manualRetry: retry.manualRetry,
    enrichWithAI,
  }
}
