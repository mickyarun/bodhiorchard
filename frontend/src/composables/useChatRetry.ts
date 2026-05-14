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
 * Single-attempt auto-retry policy for the BUD chat composable.
 *
 * The backend returns a retryable error code (``chat_reply_unparseable``)
 * when the agent's stdout could not be parsed as a structured reply. The
 * UX is: one silent auto-retry against the same session id, then a
 * manual-retry banner. Concentrating that state machine here keeps
 * ``useBudChat`` focused on orchestration; this module owns the budget
 * counter, the pending-message slot, and the banner flag.
 */

import { ref } from 'vue'

/** Backend error code that maps to the "retry once" branch. Keep in
 * lockstep with ``CHAT_REPLY_UNPARSEABLE`` in ``backend/app/services/job_chat.py``. */
export const CHAT_REPLY_UNPARSEABLE = 'chat_reply_unparseable'

export interface PendingTurn {
  msg: string
  images: string[]
}

export interface ChatRetryOptions {
  /** Resends the pending turn. Resolves true on enqueue success. */
  resend: (msg: string, images: string[]) => Promise<boolean>
  /** Surface the "retrying..." status while the auto-retry is inflight. */
  setStatus: (text: string) => void
  /** Toggle the spinner during the auto-retry round trip. */
  setLoading: (loading: boolean) => void
}

export function useChatRetry(opts: ChatRetryOptions) {
  /** Flips ``true`` after a second consecutive parse failure. */
  const retryPrompt = ref(false)
  /** Slot for the last user-authored turn so retry has something to resend. */
  const lastUserMessage = ref<PendingTurn | null>(null)
  /** Strict budget of one auto-retry per user turn. */
  let autoRetryAttempted = false

  function rememberTurn(msg: string, images: string[]): void {
    lastUserMessage.value = { msg, images }
  }

  function resetBudget(): void {
    autoRetryAttempted = false
    retryPrompt.value = false
  }

  async function maybeAutoRetry(): Promise<void> {
    const pending = lastUserMessage.value
    if (!pending) return
    if (autoRetryAttempted) {
      // Second failure in a row: flip to manual-retry banner.
      retryPrompt.value = true
      return
    }
    autoRetryAttempted = true
    opts.setStatus('Reply was malformed — retrying...')
    opts.setLoading(true)
    const ok = await opts.resend(pending.msg, pending.images)
    if (!ok) retryPrompt.value = true
  }

  function manualRetry(): void {
    const pending = lastUserMessage.value
    if (!pending) return
    retryPrompt.value = false
    autoRetryAttempted = false
    opts.setLoading(true)
    void opts.resend(pending.msg, pending.images)
  }

  return {
    retryPrompt,
    lastUserMessage,
    rememberTurn,
    resetBudget,
    maybeAutoRetry,
    manualRetry,
  }
}
