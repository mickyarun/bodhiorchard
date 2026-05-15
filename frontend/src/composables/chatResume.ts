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
 * Resume helper for the BUD chat panel.
 *
 * Split out of ``useBudChat`` so the orchestration module stays small
 * and re-mount resume can be tested in isolation. Mirrors the
 * "factory over a callback bag" shape of ``chatJobSocket.ts``.
 *
 * Behaviour: on BUD-detail remount the chat panel asks the backend
 * whether a chat job is still in flight for the current
 * ``(bud, section, design)`` thread. If so, the resume hook flips
 * ``chatLoading`` on, restores the last status line, and re-subscribes
 * via ``startTracking`` using the exact same socket-callback bag the
 * originate path uses — so resume and send share one terminal-frame
 * code path.
 */

import { makeChatSocketCallbacks } from '@/composables/chatJobSocket'
import type { SocketCallbackDeps } from '@/composables/chatJobSocket'
import type { BUDSectionKey, JobStatusRead } from '@/types'

type SocketCallbacks = ReturnType<typeof makeChatSocketCallbacks>

export interface ResumeActiveChatDeps {
  /** Returns the BUD currently rendered in the panel (or null on cold mount). */
  getBud: () => { id: string } | null
  /** Current section tab (``requirements_md`` / ``design`` / …). */
  getCurrentSection: () => BUDSectionKey
  /** Active design-tab id when the section is ``design``. */
  getDesignTabId: () => string | undefined
  /** Backend probe — null when no in-flight chat for this thread. */
  fetchActiveChatJob: (
    budId: string,
    section: string,
    designId?: string,
  ) => Promise<JobStatusRead | null>
  /** Job-socket starter from ``useJobSocket``. */
  startTracking: (jobId: string, cbs: SocketCallbacks) => void
  /** Toggles the chat panel's loading spinner. */
  setLoading: (loading: boolean) => void
  /** Updates the inline status line under the input. */
  setStatus: (text: string) => void
  /**
   * Bag of socket callbacks (pushMessage, setStatus, setLoading,
   * setSessionId, applyUpdatedContent, maybeAutoRetry) shared with
   * ``sendOnce`` so resume and originate behave identically once
   * ``startTracking`` is called.
   */
  socketCallbacks: SocketCallbackDeps
}

/**
 * Build the ``resumeActiveChat`` function from its dependency bag.
 *
 * Returns a no-arg async function the caller can chain into
 * ``loadChatHistory``. The function silently no-ops on every cold-path
 * branch (no BUD mounted, no in-flight job, lookup failed) so the
 * orchestrator doesn't need to special-case any of them.
 */
export function makeResumeActiveChat(deps: ResumeActiveChatDeps): () => Promise<void> {
  return async function resumeActiveChat(): Promise<void> {
    const bud = deps.getBud()
    if (!bud) return
    const section = deps.getCurrentSection()
    const designId = section === 'design' ? deps.getDesignTabId() : undefined
    const active = await deps.fetchActiveChatJob(bud.id, section, designId)
    if (!active) return

    deps.setLoading(true)
    deps.setStatus(active.statusMessage ?? '')
    deps.startTracking(
      active.jobId,
      makeChatSocketCallbacks(section, deps.socketCallbacks),
    )
  }
}
