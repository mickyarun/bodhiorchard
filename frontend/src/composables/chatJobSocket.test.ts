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
 * Locks the bud-id-guard contract in ``chatJobSocket``.
 *
 * The page reuses the BUDDetail component on /buds/A → /buds/B navigations
 * (same route name, different ``:id`` param), so in-flight WS callbacks
 * for A can fire after the user has switched to B. Without the guard
 * those callbacks would silently overwrite B's section content or push
 * A's reply into B's transcript — exactly the "snapped back to previous
 * BUD" symptom from the bug report. These tests assert the guard
 * short-circuits mutations once the current BUD diverges from the
 * originating one.
 */

import { describe, expect, it, vi } from 'vitest'

import { makeChatSocketCallbacks } from '@/composables/chatJobSocket'

// Return-type is intentionally loose — Vitest's ``Mock`` generic and the
// real ``SocketCallbackDeps`` strict signatures don't unify cleanly when
// intersected. The test bodies cast back via ``deps.pushMessage.mock``
// where they need the Mock surface; the ``cbs`` factory accepts the
// looser shape because ``makeChatSocketCallbacks`` only ever calls the
// methods, never reads their types.
function makeDeps(currentBudId: string | null, hasLatestAi = false) {
  return {
    pushMessage: vi.fn(),
    applyUpdatedContent: vi.fn(),
    setStatus: vi.fn(),
    setLoading: vi.fn(),
    setSessionId: vi.fn(),
    reloadHistory: vi.fn(async () => {}),
    maybeAutoRetry: vi.fn(async () => {}),
    getCurrentBudId: vi.fn(() => currentBudId),
    hasLatestAiMessage: vi.fn(() => hasLatestAi),
  }
}

const ORIG_BUD = 'bud-a-uuid'
const OTHER_BUD = 'bud-b-uuid'

describe('chatJobSocket bud-id guards', () => {
  it('onComplete pushes reply + applies content when current BUD matches origin', async () => {
    const deps = makeDeps(ORIG_BUD)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const cbs = makeChatSocketCallbacks('requirements_md', deps as any, ORIG_BUD)

    await cbs.onComplete({
      result: { reply: 'done', updated_content: 'new body', session_id: 'sess-1' },
    })

    expect(deps.setLoading).toHaveBeenCalledWith(false)
    expect(deps.setSessionId).toHaveBeenCalledWith('sess-1')
    expect(deps.pushMessage).toHaveBeenCalledWith(
      { role: 'ai', text: 'done' },
      ORIG_BUD,
    )
    expect(deps.applyUpdatedContent).toHaveBeenCalledWith(
      'requirements_md',
      'new body',
      ORIG_BUD,
    )
  })

  it('onComplete fully short-circuits when current BUD diverges', async () => {
    // All mutations (including setLoading / setSessionId) are guarded
    // because ``chatLoading`` / ``currentSessionId`` are page-local
    // refs — clearing them for a stale tracker would corrupt the new
    // BUD's flight indicator. The cross-cutting reviewer caught this
    // after the per-chunk reviewer passed.
    const deps = makeDeps(OTHER_BUD)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const cbs = makeChatSocketCallbacks('requirements_md', deps as any, ORIG_BUD)

    await cbs.onComplete({
      result: { reply: 'done', updated_content: 'new body', session_id: 'sess-2' },
    })

    expect(deps.setLoading).not.toHaveBeenCalled()
    expect(deps.setSessionId).not.toHaveBeenCalled()
    expect(deps.pushMessage).not.toHaveBeenCalled()
    expect(deps.applyUpdatedContent).not.toHaveBeenCalled()
  })

  it('onMissing fully short-circuits when current BUD diverges', async () => {
    // ``setLoading`` and ``setStatus`` are guarded now too — see the
    // ``onComplete`` test above for the same reason.
    const deps = makeDeps(OTHER_BUD)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const cbs = makeChatSocketCallbacks('requirements_md', deps as any, ORIG_BUD)

    await cbs.onMissing()

    expect(deps.setLoading).not.toHaveBeenCalled()
    expect(deps.setStatus).not.toHaveBeenCalled()
    expect(deps.reloadHistory).not.toHaveBeenCalled()
  })

  it('onMissing reloads history when current BUD still matches origin', async () => {
    const deps = makeDeps(ORIG_BUD)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const cbs = makeChatSocketCallbacks('requirements_md', deps as any, ORIG_BUD)

    await cbs.onMissing()

    expect(deps.reloadHistory).toHaveBeenCalledOnce()
  })

  it('onError fully short-circuits when current BUD diverges (no setLoading, no reload, no push)', async () => {
    // Cross-cutting reviewer caught this: ``setLoading(false)`` was
    // previously called before the bud-id guard, which cleared the
    // active BUD's flight indicator when a stale tracker fired.
    const deps = makeDeps(OTHER_BUD)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const cbs = makeChatSocketCallbacks('requirements_md', deps as any, ORIG_BUD)

    await cbs.onError('something broke', 'some_code')

    expect(deps.setLoading).not.toHaveBeenCalled()
    expect(deps.reloadHistory).not.toHaveBeenCalled()
    expect(deps.pushMessage).not.toHaveBeenCalled()
  })

  it('onError reloads + skips fallback push when the persisted failure row landed', async () => {
    // Happy path: worker persisted the marker, reload picked it up,
    // the latest message in the transcript is now AI-side. No
    // in-memory push needed.
    const deps = makeDeps(ORIG_BUD, /* hasLatestAi */ true)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const cbs = makeChatSocketCallbacks('requirements_md', deps as any, ORIG_BUD)

    await cbs.onError('something broke', 'some_code')

    expect(deps.setLoading).toHaveBeenCalledWith(false)
    expect(deps.reloadHistory).toHaveBeenCalledOnce()
    expect(deps.pushMessage).not.toHaveBeenCalled()
  })

  it('onError pushes friendly fallback when reload returns no AI marker (covers persist-failed silent-failure path)', async () => {
    // Worker's persist_chat_message itself raised (DB hiccup). Reload
    // returns without an AI row. Without the fallback push the user
    // would see the spinner stop and a thread that ends in their own
    // prompt — exactly the silent-failure pattern flagged by the
    // silent-failure-hunter on this chunk.
    const deps = makeDeps(ORIG_BUD, /* hasLatestAi */ false)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const cbs = makeChatSocketCallbacks('requirements_md', deps as any, ORIG_BUD)

    await cbs.onError('something broke', 'some_code')

    expect(deps.reloadHistory).toHaveBeenCalledOnce()
    expect(deps.pushMessage).toHaveBeenCalledOnce()
    const [msg, budId] = deps.pushMessage.mock.calls[0]!
    expect(msg.role).toBe('ai')
    expect(budId).toBe(ORIG_BUD)
  })

  it('onError still routes chat_reply_unparseable to auto-retry', async () => {
    const deps = makeDeps(ORIG_BUD)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const cbs = makeChatSocketCallbacks('requirements_md', deps as any, ORIG_BUD)

    await cbs.onError('Reply was malformed.', 'chat_reply_unparseable')

    expect(deps.maybeAutoRetry).toHaveBeenCalledOnce()
    // Auto-retry path: no reload, no push — useChatRetry handles it.
    expect(deps.reloadHistory).not.toHaveBeenCalled()
    expect(deps.pushMessage).not.toHaveBeenCalled()
  })

  it('onProgress short-circuits when current BUD diverges', async () => {
    // ``setStatus`` is now guarded — the prior "harmless cross-BUD"
    // assumption was wrong because ``chatStatusMessage`` is a shared
    // ref. Cross-cutting reviewer flagged this.
    const deps = makeDeps(OTHER_BUD)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const cbs = makeChatSocketCallbacks('requirements_md', deps as any, ORIG_BUD)

    cbs.onProgress({ statusMessage: 'working' })

    expect(deps.setStatus).not.toHaveBeenCalled()
  })

  it('onProgress forwards status when current BUD matches origin', async () => {
    const deps = makeDeps(ORIG_BUD)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const cbs = makeChatSocketCallbacks('requirements_md', deps as any, ORIG_BUD)

    cbs.onProgress({ statusMessage: 'working' })

    expect(deps.setStatus).toHaveBeenCalledWith('working')
  })
})
