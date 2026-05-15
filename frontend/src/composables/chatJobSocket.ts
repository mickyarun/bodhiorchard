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
 * Job-socket callback wiring for the BUD chat composable.
 *
 * Split out of ``useBudChat`` so the orchestration module stays focused
 * on send/abort and state, and the socket-event handlers — which are
 * pure functions over a callback bag — live in their own module.
 */

import { friendlyAgentError } from '@/types/agentErrors'
import { CHAT_REPLY_UNPARSEABLE } from '@/composables/useChatRetry'
import type { BUDSectionKey } from '@/types'
import type { ChatMessage } from '@/composables/useBudChat'

export interface ChatJobResult {
  reply?: string
  updated_content?: string | null
  session_id?: string
  rotated_session?: boolean
  retryable?: boolean
}

export interface SocketCallbackDeps {
  /** Push an AI message into the visible transcript. */
  pushMessage: (m: ChatMessage) => void
  /** Update the inline status line under the input. */
  setStatus: (text: string) => void
  /** Toggle the input spinner. */
  setLoading: (loading: boolean) => void
  /** Worker echoes a (possibly rotated) session id on completion. */
  setSessionId: (id: string) => void
  /** Mirror returned content into the right surface (editor or design tab). */
  applyUpdatedContent: (section: BUDSectionKey, content: string) => void | Promise<void>
  /** Auto-retry hook for ``chat_reply_unparseable`` errors. */
  maybeAutoRetry: () => Promise<void>
  /**
   * Re-fetch persisted chat messages from the backend. Used by the
   * 404-recovery hook below so the user sees the boot-time orphan
   * marker (or any other newly-persisted row) without a manual
   * refresh.
   */
  reloadHistory: () => Promise<void>
}

export function makeChatSocketCallbacks(section: BUDSectionKey, deps: SocketCallbackDeps) {
  return {
    onProgress(status: { statusMessage: string }) {
      deps.setStatus(status.statusMessage)
    },
    async onComplete(data: unknown) {
      deps.setLoading(false)
      const parsed = (data as Record<string, unknown>).result as ChatJobResult | null
      // Worker may have rotated the row at the cap — pick up the fresh
      // id transparently so subsequent turns resume the new session.
      if (parsed?.session_id) deps.setSessionId(parsed.session_id)
      const reply = parsed?.reply || ''
      const updatedContent = parsed?.updated_content ?? null
      if (reply) deps.pushMessage({ role: 'ai', text: reply })
      if (updatedContent !== null) {
        await deps.applyUpdatedContent(section, updatedContent)
      }
    },
    async onError(err: string, errorCode?: string | null) {
      deps.setLoading(false)
      if (errorCode === CHAT_REPLY_UNPARSEABLE) {
        await deps.maybeAutoRetry()
        return
      }
      deps.pushMessage({
        role: 'ai',
        text: friendlyAgentError(errorCode, err).headline,
      })
    },
    async onMissing() {
      // Backend restarted (or terminal TTL reaped) mid-chat — the
      // WS terminal frame never arrived, so the spinner is stuck.
      // Drop loading and reload chat-history so the orphan-sweep
      // marker (or the cancel marker, if cancel raced the eviction)
      // shows in the thread automatically; the user doesn't need to
      // refresh the page to see what happened.
      deps.setLoading(false)
      deps.setStatus('')
      await deps.reloadHistory()
    },
  }
}
