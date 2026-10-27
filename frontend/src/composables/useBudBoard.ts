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

// State for the BUD board: filters, the columns to show, and the data
// loading (BUD list, stage settings, team summaries, refresh on new
// notifications).

import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useBUDStore } from '@/stores/bud'
import { useNotificationStore } from '@/stores/notifications'
import { useSettingsStore } from '@/stores/settings'
import { useTeamsStore } from '@/stores/teams'
import { usePhaseOrder } from '@/composables/usePhaseOrder'
import { BUD_PRIORITIES, type BUDPriority, type BUDStatus } from '@/types'
import { assigneeOptions, filterBoard, type FilterOption } from '@/utils/budBoard'

export function useBudBoard() {
  const budStore = useBUDStore()
  const settingsStore = useSettingsStore()
  const teamsStore = useTeamsStore()
  const { phaseOrder } = usePhaseOrder()

  const query = ref('')
  const assignee = ref<string | null>(null)
  const priority = ref<BUDPriority | null>(null)
  const team = ref<string | null>(null)
  const sortByPriority = ref(false)
  // Discarded BUDs are terminal, so they stay off the board until asked
  // for; the toggle appends them as a trailing column for review and restore.
  const showDiscarded = ref(false)

  const priorityOptions: FilterOption<BUDPriority>[] = BUD_PRIORITIES.map(p => ({ value: p, label: p }))
  const assignees = computed(() => assigneeOptions(budStore.buds))
  const teamOptions = computed<FilterOption[]>(() =>
    teamsStore.activeTeams.map(t => ({ value: t.id, label: t.name })),
  )

  // The team summary list carries no members, so the picked team's detail
  // is fetched on demand. Until it arrives the filter matches nothing
  // rather than briefly showing every BUD.
  watch(team, async (id) => {
    if (id && !teamsStore.detailsById[id]) await teamsStore.fetchTeam(id)
  })
  const teamMemberIds = computed<ReadonlySet<string> | null>(() => {
    if (!team.value) return null
    const detail = teamsStore.detailsById[team.value]
    return new Set(detail ? detail.members.map(m => m.user_id) : [])
  })

  const columns = computed<BUDStatus[]>(() =>
    phaseOrder.value.filter(s => s !== 'discarded' || showDiscarded.value),
  )
  const budsByColumn = computed(() =>
    filterBoard(budStore.budsByStatus, {
      query: query.value ?? '',
      assignee: assignee.value,
      priority: priority.value,
      teamMemberIds: teamMemberIds.value,
      sortByPriority: sortByPriority.value,
    }),
  )
  const shownCount = computed(() =>
    columns.value.reduce((n, s) => n + (budsByColumn.value[s]?.length ?? 0), 0),
  )
  const filtering = computed(() => Boolean(query.value?.trim() || assignee.value || priority.value || team.value))

  onMounted(() => {
    void budStore.fetchBUDs()
    // usePhaseOrder reads the org's UAT toggle; without this a cold load
    // would always show the UAT column.
    if (!settingsStore.connectionsLoaded) void settingsStore.fetchConnections()
    // Team summaries feed the Team filter; members load per team on pick.
    if (teamsStore.teams.length === 0) void teamsStore.fetchTeams(false)
  })

  // A new notification usually means an agent finished work on some BUD,
  // so refetch the list to keep the cards current without a page reload.
  const { items: notifications } = storeToRefs(useNotificationStore())
  watch(
    () => notifications.value.length,
    (len, prev) => {
      if (len > (prev ?? 0)) void budStore.fetchBUDs()
    },
  )

  return {
    budStore,
    query,
    assignee,
    priority,
    team,
    sortByPriority,
    showDiscarded,
    priorityOptions,
    assignees,
    teamOptions,
    columns,
    budsByColumn,
    shownCount,
    filtering,
  }
}
