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
 * The BUD board's state: columns follow the org's stages, discarded BUDs
 * only on request, the team filter shows nothing until the team's members
 * arrive, and a new notification refetches the list. Mounted in a host
 * component so its onMounted loads run.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h as render, nextTick, reactive, ref, type Ref } from 'vue'

const h = vi.hoisted(() => ({
  bud: { buds: [] as unknown[], budsByStatus: {} as Record<string, unknown[]>, fetchBUDs: vi.fn() },
  settings: { connectionsLoaded: false, connections: {} as Record<string, unknown>, fetchConnections: vi.fn() },
  teams: {
    teams: [] as unknown[],
    activeTeams: [] as { id: string; name: string }[],
    detailsById: {} as Record<string, { members: { user_id: string }[] }>,
    fetchTeams: vi.fn(),
    fetchTeam: vi.fn(),
  },
  // storeToRefs keeps only refs and reactive values, as on a real store.
  notifications: { items: null as unknown as Ref<unknown[]> },
}))
vi.mock('@/stores/bud', () => ({ useBUDStore: () => h.bud }))
vi.mock('@/stores/settings', () => ({ useSettingsStore: () => h.settings }))
vi.mock('@/stores/teams', () => ({ useTeamsStore: () => h.teams }))
vi.mock('@/stores/notifications', () => ({ useNotificationStore: () => h.notifications }))

import { useBudBoard } from '@/composables/useBudBoard'

const BUDS = [
  { id: '1', title: 'Passkeys', status: 'bud', priority: 'P1', assignee_id: 'ana', assignee_name: 'Ana', bud_number: 1 },
  { id: '2', title: 'Refunds', status: 'design', priority: 'P0', assignee_id: 'raj', assignee_name: 'Raj', bud_number: 2 },
  { id: '3', title: 'Old idea', status: 'discarded', priority: 'P3', assignee_id: null, bud_number: 3 },
]

function group(buds: typeof BUDS): Record<string, unknown[]> {
  const out: Record<string, unknown[]> = {}
  for (const b of buds) (out[b.status] ??= []).push(b)
  return out
}

function mountBoard(): ReturnType<typeof useBudBoard> {
  let board!: ReturnType<typeof useBudBoard>
  mount(defineComponent({ setup() { board = useBudBoard(); return () => render('div') } }))
  return board
}

beforeEach(() => {
  vi.clearAllMocks()
  h.bud.buds = BUDS
  h.bud.budsByStatus = reactive(group(BUDS))
  h.settings.connectionsLoaded = false
  h.settings.connections = reactive({ budStages: { uatEnabled: true } })
  h.teams.teams = []
  h.teams.activeTeams = [{ id: 't1', name: 'Payments' }]
  h.teams.detailsById = reactive({})
  h.notifications = { items: ref([]) }
})

describe('useBudBoard', () => {
  it('loads the list, the stage settings and the teams on mount', () => {
    mountBoard()
    expect(h.bud.fetchBUDs).toHaveBeenCalledOnce()
    expect(h.settings.fetchConnections).toHaveBeenCalledOnce()
    expect(h.teams.fetchTeams).toHaveBeenCalledWith(false)
  })

  it('does not refetch settings or teams it already has', () => {
    h.settings.connectionsLoaded = true
    h.teams.teams = [{ id: 't1' }]
    mountBoard()
    expect(h.settings.fetchConnections).not.toHaveBeenCalled()
    expect(h.teams.fetchTeams).not.toHaveBeenCalled()
  })

  it('shows discarded BUDs only once asked, as the last column', () => {
    const board = mountBoard()
    expect(board.columns.value).not.toContain('discarded')
    expect(board.shownCount.value).toBe(2)
    board.showDiscarded.value = true
    expect(board.columns.value.at(-1)).toBe('discarded')
    expect(board.shownCount.value).toBe(3)
  })

  it('drops the UAT column when the org has no UAT stage', () => {
    h.settings.connections = reactive({ budStages: { uatEnabled: false } })
    expect(mountBoard().columns.value).not.toContain('uat')
  })

  it('filters by text and priority, and says it is filtering', () => {
    const board = mountBoard()
    expect(board.filtering.value).toBe(false)
    board.query.value = 'bud-002'
    expect(board.shownCount.value).toBe(1)
    expect(board.filtering.value).toBe(true)
    board.query.value = '   '
    expect(board.filtering.value).toBe(false)
    board.priority.value = 'P1'
    expect(board.budsByColumn.value.bud).toHaveLength(1)
    expect(board.budsByColumn.value.design).toHaveLength(0)
  })

  it('matches nothing under a team filter until its members arrive', async () => {
    h.teams.fetchTeam.mockImplementation(async (id: string) => {
      h.teams.detailsById[id] = { members: [{ user_id: 'raj' }] }
    })
    const board = mountBoard()
    board.team.value = 't1'
    expect(board.shownCount.value).toBe(0)
    await flushPromises()
    expect(h.teams.fetchTeam).toHaveBeenCalledWith('t1')
    expect(board.shownCount.value).toBe(1)
    expect(board.budsByColumn.value.design).toEqual([BUDS[1]])
  })

  it('does not refetch a team it already knows', async () => {
    h.teams.detailsById.t1 = { members: [] }
    const board = mountBoard()
    board.team.value = 't1'
    await flushPromises()
    expect(h.teams.fetchTeam).not.toHaveBeenCalled()
  })

  it('offers the team list and every assignee, with Unassigned last', () => {
    const board = mountBoard()
    expect(board.teamOptions.value).toEqual([{ value: 't1', label: 'Payments' }])
    expect(board.assignees.value.map(a => a.label)).toEqual(['Ana', 'Raj', 'Unassigned'])
  })

  it('refetches the list when a notification arrives, not when one is read away', async () => {
    mountBoard()
    h.notifications.items.value.push({ id: 'n1' })
    await nextTick()
    expect(h.bud.fetchBUDs).toHaveBeenCalledTimes(2)
    h.notifications.items.value.pop()
    await nextTick()
    expect(h.bud.fetchBUDs).toHaveBeenCalledTimes(2)
  })
})
