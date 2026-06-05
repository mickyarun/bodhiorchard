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
  /**
   * Push an AI message into the visible transcript. Takes the
   * originating BUD id so the implementation can skip the mutation
   * when the user has navigated to a different BUD mid-flight.
   */
  pushMessage: (m: ChatMessage, originatingBudId: string) => void
  /** Update the inline status line under the input. */
  setStatus: (text: string) => void
  /** Toggle the input spinner. */
  setLoading: (loading: boolean) => void
  /** Worker echoes a (possibly rotated) session id on completion. */
  setSessionId: (id: string) => void
  /**
   * Mirror returned content into the right surface (editor or design
   * tab). BUD-id-guarded by the implementation: skipped silently when
   * the page now shows a different BUD than the one this job started on.
   */
  applyUpdatedContent: (
    section: BUDSectionKey,
    content: string,
    originatingBudId: string,
  ) => void | Promise<void>
  /** Auto-retry hook for ``chat_reply_unparseable`` errors. */
  maybeAutoRetry: () => Promise<void>
  /**
   * Re-fetch persisted chat messages from the backend. Used by the
   * 404-recovery hook below so the user sees the boot-time orphan
   * marker (or any other newly-persisted row) without a manual
   * refresh.
   */
  reloadHistory: () => Promise<void>
  /** Returns the BUD id currently rendered by the page, or null. */
  getCurrentBudId: () => string | null
  /**
   * True iff the latest message in the visible transcript is from the
   * AI. Used by ``onError`` to detect the "persist failed AND reload
   * left the thread missing the failure marker" silent-failure path
   * — the only case where the in-memory fallback push needs to fire.
   */
  hasLatestAiMessage: () => boolean
}

export function makeChatSocketCallbacks(
  section: BUDSectionKey,
  deps: SocketCallbackDeps,
  originatingBudId: string,
) {
  // Predicate hoisted so every callback applies the same guard:
  // when the user navigates BUD A → BUD B mid-flight, in-flight WS
  // frames for A must not mutate B's transcript, section content, OR
  // page-local state like the loading spinner and status line. The
  // earlier "setLoading is harmless cross-BUD" rationale was wrong —
  // ``chatLoading`` is a single ref shared across the composable
  // instance, so clearing it for A's stale tracker would also clear
  // B's flight indicator if B has a chat in progress.
  const isCurrentBud = () => deps.getCurrentBudId() === originatingBudId

  return {
    onProgress(status: { statusMessage: string }) {
      if (!isCurrentBud()) return
      deps.setStatus(status.statusMessage)
    },
    async onComplete(data: unknown) {
      if (!isCurrentBud()) return
      deps.setLoading(false)
      const parsed = (data as Record<string, unknown>).result as ChatJobResult | null
      // Worker may have rotated the row at the cap — pick up the fresh
      // id transparently so subsequent turns resume the new session.
      if (parsed?.session_id) deps.setSessionId(parsed.session_id)
      const reply = parsed?.reply || ''
      const updatedContent = parsed?.updated_content ?? null
      if (reply) deps.pushMessage({ role: 'ai', text: reply }, originatingBudId)
      if (updatedContent !== null) {
        await deps.applyUpdatedContent(section, updatedContent, originatingBudId)
      }
    },
    async onError(err: string, errorCode?: string | null) {
      if (errorCode === CHAT_REPLY_UNPARSEABLE) {
        // Auto-retry path is BUD-id agnostic — it re-fires the same
        // chat job, which routes back through ``useChatRetry``'s
        // budget check. The retry itself will use the originating
        // BUD's getBud() so cross-BUD send-on-stale-retry is blocked
        // there.
        await deps.maybeAutoRetry()
        return
      }
      if (!isCurrentBud()) return
      deps.setLoading(false)
      // Two-step recovery:
      // 1. Reload chat history — the worker persists an AI-role
      //    failure row to the DB before the WS terminal frame fires
      //    (see ``job_chat.py``'s ``persist_chat_message`` calls in
      //    both failure branches and the cancel marker), so reload
      //    picks up the persisted marker. This is the source of truth.
      // 2. Fallback push if the reload didn't surface an AI reply —
      //    covers the silent-failure path where the worker's
      //    ``persist_chat_message`` itself raised and only the log
      //    line caught it. Without this, the user would see the
      //    spinner stop and an unchanged thread (no banner, no row).
      await deps.reloadHistory()
      if (!deps.hasLatestAiMessage()) {
        deps.pushMessage(
          { role: 'ai', text: friendlyAgentError(errorCode, err).headline },
          originatingBudId,
        )
      }
    },
    async onMissing() {
      // Backend restarted (or terminal TTL reaped) mid-chat — the
      // WS terminal frame never arrived, so the spinner is stuck.
      // Drop loading and reload chat-history so the orphan-sweep
      // marker (or the cancel marker, if cancel raced the eviction)
      // shows in the thread automatically; the user doesn't need to
      // refresh the page to see what happened. All three mutations
      // gate on ``isCurrentBud`` so a stale tracker for the prior
      // BUD can't clear the active BUD's spinner / status mid-chat.
      if (!isCurrentBud()) return
      deps.setLoading(false)
      deps.setStatus('')
      await deps.reloadHistory()
    },
  }
}
