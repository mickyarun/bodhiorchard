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
 * AbortController-backed loader for BUD chat history.
 *
 * Stale fetches are common: the user switches sections rapidly, or a
 * fetch races with a fresh chat push, and the older response would
 * otherwise overwrite the newer state. This composable owns the
 * single in-flight ``AbortController`` so callers can request a
 * reload without worrying about cancellation bookkeeping.
 */

import type { ChatMessageRead } from '@/types'

export interface ChatHistoryLoaderOptions {
  /** Lazily-evaluated BUD id; ``null`` when the page hasn't loaded yet. */
  getBudId: () => string | null
  /** Active section + optional design id for filter scope. */
  getScope: () => { section: string, designId?: string }
  /** Optional session id filter; passed through as-is to the API. */
  getSessionId: () => string | undefined
  /** Backing store call. ``signal`` MUST be threaded into the HTTP client. */
  fetch: (
    budId: string,
    section: string,
    designId: string | undefined,
    sessionId: string | undefined,
    signal: AbortSignal,
  ) => Promise<ChatMessageRead[]>
}

export function useChatHistoryLoader(opts: ChatHistoryLoaderOptions) {
  let inflight: AbortController | null = null

  /** Aborts whatever's running. Safe to call when nothing is in flight. */
  function abortInflight(): void {
    if (inflight) inflight.abort()
    inflight = null
  }

  /** Resolves to messages, or ``null`` if the fetch was superseded. */
  async function load(): Promise<ChatMessageRead[] | null> {
    const budId = opts.getBudId()
    if (!budId) return null
    abortInflight()
    const ctrl = new AbortController()
    inflight = ctrl
    const { section, designId } = opts.getScope()
    const sessionId = opts.getSessionId()
    const history = await opts.fetch(budId, section, designId, sessionId, ctrl.signal)
    // A newer call may have aborted us between awaits; drop the stale result.
    if (ctrl.signal.aborted) return null
    return history
  }

  return { load, abortInflight }
}
