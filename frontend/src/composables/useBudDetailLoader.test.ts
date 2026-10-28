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
 * Loading the BUD in the route: the tab it opens on (a valid ``?tab=``
 * wins, otherwise the BUD's stage), and a load overtaken by a move to
 * another BUD stopping before it touches the page or the live channel.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, effectScope, nextTick, reactive, ref, type EffectScope } from 'vue'
import type { BUDDocument, BUDStatus } from '@/types'

const h = vi.hoisted(() => ({
  route: { params: { id: '' }, query: {} as Record<string, string> },
  fetchBUD: vi.fn(),
  channel: { connect: vi.fn(), disconnect: vi.fn() },
  settings: { connectionsLoaded: false, repos: [] as unknown[], fetchConnections: vi.fn(), fetchRepos: vi.fn() },
  fetchMembers: vi.fn(),
}))
vi.mock('vue-router', () => ({ useRoute: () => h.route }))
vi.mock('@/stores/bud', () => ({
  useBUDStore: () => ({ fetchBUD: h.fetchBUD, refreshBUDIfCurrent: vi.fn() }),
}))
vi.mock('@/stores/members', () => ({ useMembersStore: () => ({ fetchMembers: h.fetchMembers }) }))
vi.mock('@/stores/settings', () => ({ useSettingsStore: () => h.settings }))
vi.mock('@/composables/useBudActivityChannel', () => ({ useBudActivityChannel: () => h.channel }))

import { useBudDetailLoader } from '@/composables/useBudDetailLoader'

const current = ref<BUDDocument | null>(null)
const activeTab = ref('requirements')
const hooks = {
  bud: computed(() => current.value),
  activeTab,
  startNewSession: vi.fn(),
  loadChatHistory: vi.fn(async () => undefined),
  loadTimeline: vi.fn(async () => undefined),
  reloadEstimates: vi.fn(),
  onLearningRecorded: vi.fn(),
}

/** fetchBUD resolves per id when the test says so, and then shows that BUD. */
const pending = new Map<string, () => void>()
function arriving(id: string, status: BUDStatus): void {
  h.fetchBUD.mockImplementationOnce(() => new Promise<void>(resolve => {
    pending.set(id, () => {
      current.value = { id, status } as unknown as BUDDocument
      resolve()
    })
  }))
}
async function settle(): Promise<void> {
  for (let i = 0; i < 5; i++) await Promise.resolve()
}

let scope: EffectScope

function open(id: string, query: Record<string, string> = {}) {
  h.route = reactive({ params: { id }, query })
  scope = effectScope()
  return scope.run(() => useBudDetailLoader(hooks))!
}

beforeEach(() => {
  vi.clearAllMocks()
  pending.clear()
  current.value = null
  activeTab.value = 'requirements'
  h.settings.connectionsLoaded = false
  h.settings.repos = []
})

afterEach(() => scope.stop())

describe('useBudDetailLoader', () => {
  it('opens the tab for the BUD stage and connects its live channel', async () => {
    arriving('A', 'testing')
    open('A')
    pending.get('A')!()
    await settle()
    expect(activeTab.value).toBe('testing')
    expect(h.channel.connect).toHaveBeenCalledWith('A')
    expect(h.fetchMembers).toHaveBeenCalled()
    expect(h.settings.fetchConnections).toHaveBeenCalled()
    expect(h.settings.fetchRepos).toHaveBeenCalled()
  })

  it.each(['uat', 'prod', 'closed', 'tech-spec'])('keeps a valid ?tab=%s link', async (tab) => {
    arriving('A', 'bud')
    open('A', { tab })
    expect(activeTab.value).toBe(tab)
    pending.get('A')!()
    await settle()
    expect(activeTab.value).toBe(tab)
  })

  it('never opens an unknown ?tab= value', async () => {
    arriving('A', 'code_review')
    open('A', { tab: 'nonsense' })
    pending.get('A')!()
    await settle()
    expect(activeTab.value).not.toBe('nonsense')
  })

  it('opens a discarded BUD on its Closed tab', async () => {
    arriving('A', 'discarded')
    open('A')
    pending.get('A')!()
    await settle()
    expect(activeTab.value).toBe('closed')
  })

  it('stops a load that a move to another BUD overtook', async () => {
    arriving('A', 'testing')
    arriving('B', 'design')
    open('A')
    h.route.params.id = 'B'
    await nextTick()
    expect(h.channel.disconnect).toHaveBeenCalledTimes(2)

    pending.get('B')!()
    await settle()
    pending.get('A')!()
    await settle()

    expect(activeTab.value).toBe('design')
    expect(h.channel.connect).toHaveBeenCalledTimes(1)
    expect(h.channel.connect).toHaveBeenCalledWith('B')
    expect(hooks.loadChatHistory).toHaveBeenCalledTimes(1)
  })

  it('does not refetch settings the page already has', async () => {
    h.settings.connectionsLoaded = true
    h.settings.repos = [{ id: 'r1' }]
    arriving('A', 'bud')
    open('A')
    pending.get('A')!()
    await settle()
    expect(h.settings.fetchConnections).not.toHaveBeenCalled()
    expect(h.settings.fetchRepos).not.toHaveBeenCalled()
  })

  it('keeps the current tab when the BUD did not load', async () => {
    h.fetchBUD.mockResolvedValueOnce(undefined)
    activeTab.value = 'design'
    open('A')
    await settle()
    expect(activeTab.value).toBe('design')
  })

  it('loads the route BUD again on reload', async () => {
    arriving('A', 'bud')
    const loader = open('A')
    pending.get('A')!()
    await settle()
    arriving('A', 'design')
    loader.reload()
    pending.get('A')!()
    await settle()
    expect(h.fetchBUD).toHaveBeenCalledTimes(2)
    expect(h.channel.connect).toHaveBeenCalledTimes(2)
    expect(activeTab.value).toBe('design')
  })
})
