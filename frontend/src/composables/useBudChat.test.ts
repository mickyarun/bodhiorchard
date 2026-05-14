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
 * Behaviour tests for the BUD chat composable.
 *
 * Mocks the BUD store and the job tracker so the composable can be
 * exercised in pure JS with no DOM. Covers:
 *
 * - 409 stage-gate response → banner is set, optimistic user push is
 *   rolled back, the job tracker is NOT invoked.
 * - Successful send + ``chat_reply_unparseable`` onError → auto-retry
 *   once with the same session id; a second failure surfaces the
 *   manual retry banner.
 * - Rotation: ``result.session_id`` on the job result overwrites the
 *   composable's tracked id transparently.
 * - ``loadChatHistory`` aborts any prior in-flight history fetch via
 *   the AbortController plumbing.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { effectScope, ref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { useBudChat } from './useBudChat'

type SocketCallbacks = {
  onProgress?: (s: { statusMessage: string }) => void
  onComplete?: (data: unknown) => void | Promise<void>
  onError?: (err: string, errorCode?: string) => void | Promise<void>
}

const startTracking = vi.fn<[string, SocketCallbacks], void>()

vi.mock('@/composables/useJobSocket', () => ({
  useJobSocket: () => ({ startTracking }),
}))

const chatBUD = vi.fn()
const fetchChatHistory = vi.fn()

vi.mock('@/stores/bud', () => ({
  useBUDStore: () => ({
    chatBUD,
    fetchChatHistory,
    currentBUD: ref<Record<string, unknown> | null>(null),
  }),
}))

function makeHooks() {
  return {
    getBud: () => ({ id: 'bud-1' } as { id: string }),
    getCurrentSection: () => 'requirements_md' as const,
    getDesignTabId: () => undefined,
    setActiveTab: vi.fn(),
    syncEditor: vi.fn(),
    onDesignContentUpdated: vi.fn(),
  }
}

describe('useBudChat', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    startTracking.mockReset()
    chatBUD.mockReset()
    fetchChatHistory.mockReset()
  })

  it('rolls back optimistic push and surfaces banner on 409', async () => {
    chatBUD.mockResolvedValue({ stageGateError: 'Move BUD to design first.' })

    await effectScope().run(async () => {
      const chat = useBudChat(makeHooks() as never)
      await chat.handleChatSend('hi', [])

      expect(chat.stageGateMessage.value).toBe('Move BUD to design first.')
      // Optimistic user push must be rolled back.
      expect(chat.chatMessages.value.length).toBe(0)
      expect(chat.chatLoading.value).toBe(false)
      // Job tracker NOT engaged on a 409.
      expect(startTracking).not.toHaveBeenCalled()
    })
  })

  it('auto-retries once on chat_reply_unparseable then shows manual retry banner', async () => {
    chatBUD.mockResolvedValue({ jobId: 'job-1', sessionId: 'sess-1' })

    let callbacks: SocketCallbacks | undefined
    startTracking.mockImplementation((_jobId, cbs) => {
      callbacks = cbs
    })

    await effectScope().run(async () => {
      const chat = useBudChat(makeHooks() as never)
      await chat.handleChatSend('iterate', [])

      // Simulate the first parse-unparseable error from the worker.
      chatBUD.mockResolvedValueOnce({ jobId: 'job-2', sessionId: 'sess-1' })
      await callbacks?.onError?.('Reply was malformed.', 'chat_reply_unparseable')

      // The auto-retry must have re-called chatBUD once.
      expect(chatBUD).toHaveBeenCalledTimes(2)
      expect(chat.retryPrompt.value).toBe(false)

      // Simulate the retry also failing.
      await callbacks?.onError?.('Reply was malformed.', 'chat_reply_unparseable')

      // No third call. Manual retry banner is up.
      expect(chatBUD).toHaveBeenCalledTimes(2)
      expect(chat.retryPrompt.value).toBe(true)
    })
  })

  it('updates session id when worker rotates at the cap', async () => {
    chatBUD.mockResolvedValue({ jobId: 'job-r', sessionId: 'sess-old' })
    let callbacks: SocketCallbacks | undefined
    startTracking.mockImplementation((_jobId, cbs) => {
      callbacks = cbs
    })

    await effectScope().run(async () => {
      const chat = useBudChat(makeHooks() as never)
      await chat.handleChatSend('msg', [])

      await callbacks?.onComplete?.({
        result: {
          reply: 'ok',
          updated_content: null,
          session_id: 'sess-NEW',
          rotated_session: true,
        },
      })

      expect(chat.currentSessionId.value).toBe('sess-NEW')
    })
  })

  it('aborts in-flight loadChatHistory when a newer load starts', async () => {
    const seenSignals: AbortSignal[] = []
    fetchChatHistory.mockImplementation(
      async (_b: string, _s: string, _d: unknown, _ses: unknown, signal: AbortSignal) => {
        seenSignals.push(signal)
        // Resolves either when the test continues or when aborted.
        if (signal.aborted) return []
        await new Promise<void>((resolve) => {
          signal.addEventListener('abort', () => resolve())
          // Also resolve after a microtask so the second call (which
          // isn't aborted) can settle naturally.
          setTimeout(() => resolve(), 10)
        })
        return []
      },
    )

    await effectScope().run(async () => {
      const chat = useBudChat(makeHooks() as never)
      const first = chat.loadChatHistory()
      const second = chat.loadChatHistory()
      await Promise.all([first, second])

      // The first signal must be aborted by the second call's start.
      expect(seenSignals[0].aborted).toBe(true)
      expect(seenSignals[1].aborted).toBe(false)
    })
  })
})
