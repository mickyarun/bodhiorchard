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

import { computed, onMounted, ref } from 'vue'
import api from '@/services/api'
import { usePermissions } from '@/composables/usePermissions'
import { usePhaseOrder } from '@/composables/usePhaseOrder'
import { useBUDStore } from '@/stores/bud'
import { useLeaveStore } from '@/stores/leave'
import { useSettingsStore } from '@/stores/settings'
import type { CalendarEntry, CalendarRead } from '@/types/leave'
import { attentionItems, flowStages, isInFlight, overviewKpis } from '@/utils/dashboardOverview'
import { extractApiError } from '@/utils/errors'
import { addDays, toIsoDate } from '@/utils/leaveDates'

const ATTENTION_LIMIT = 5
const TIME_OFF_DAYS = 21
const TIME_OFF_LIMIT = 4

/**
 * Everything the overview needs beyond the garden data: the BUD list for
 * key numbers, flow and attention; the approver's pending leave count; and
 * leave starting in the next three weeks.
 */
export function useDashboardOverview() {
  const budStore = useBUDStore()
  const settingsStore = useSettingsStore()
  const { phaseOrder } = usePhaseOrder()
  const leaveStore = useLeaveStore()
  const { hasPermission, canViewConnections } = usePermissions()
  /** Support and other roles without it see the people cards only. */
  const canViewBuds = computed(() => hasPermission('buds:view'))
  const budLoadError = ref('')

  const timeOff = ref<CalendarEntry[]>([])
  const timeOffError = ref('')

  /** The approver's queue size; null for people who approve nothing. */
  const pendingLeave = computed(() =>
    leaveStore.approvalCount.is_approver ? leaveStore.approvalCount.pending : null,
  )
  const uatEnabled = computed(() => phaseOrder.value.includes('uat'))
  const inFlight = computed(() => budStore.buds.filter(isInFlight))
  const peopleInFlight = computed(
    () => new Set(inFlight.value.map(b => b.assignee_id).filter(Boolean)).size,
  )
  const kpis = computed(() => overviewKpis(budStore.buds, pendingLeave.value, uatEnabled.value))
  const stages = computed(() => flowStages(budStore.buds, phaseOrder.value))
  const attention = computed(() =>
    attentionItems(budStore.buds, ATTENTION_LIMIT, hasPermission('buds:approve')))

  async function loadTimeOff(): Promise<void> {
    const start = toIsoDate(new Date())
    timeOffError.value = ''
    try {
      const { data } = await api.get<CalendarRead>('/v1/leave/calendar', {
        params: { start, end: addDays(start, TIME_OFF_DAYS) },
      })
      timeOff.value = data.entries
        .filter(e => e.kind !== 'wfh' && (e.status === 'approved' || e.status === 'pending'))
        .sort((a, b) => a.start_date.localeCompare(b.start_date))
        .slice(0, TIME_OFF_LIMIT)
    } catch (err) {
      timeOff.value = []
      timeOffError.value = extractApiError(err, "Couldn't load upcoming time off.")
    }
  }

  async function loadBuds(): Promise<void> {
    await budStore.fetchBUDs()
    // Read once here: the store's error is shared with create and update.
    budLoadError.value = budStore.error
  }

  onMounted(() => {
    if (canViewBuds.value) void loadBuds()
    // The phase order needs the org's UAT setting; without access to it
    // the phase order assumes UAT is on, as the board does.
    if (canViewConnections.value && !settingsStore.connectionsLoaded) {
      void settingsStore.fetchConnections()
    }
    void leaveStore.fetchApprovalCount()
    void loadTimeOff()
  })

  return {
    canViewBuds,
    loading: computed(() => budStore.loading && budStore.buds.length === 0),
    error: budLoadError,
    inFlightCount: computed(() => inFlight.value.length),
    peopleInFlight,
    kpis,
    stages,
    attention,
    pendingLeave,
    timeOff,
    timeOffError,
  }
}
