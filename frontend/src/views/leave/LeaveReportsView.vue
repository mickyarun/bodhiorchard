<!--
 * Copyright 2025-2026 Arun Rajkumar
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 -->

<!-- Leave reports: employee-wise summary, every request, and balances, with
     filters and CSV export. HR and the owner see everyone; managers see
     their direct reports. Reasons never appear here. -->
<template>
  <div class="pa-6 reports">
    <div class="d-flex align-start justify-space-between flex-wrap ga-3 mb-4">
      <div>
        <h1 class="text-h5 font-weight-bold bo-display">Leave reports</h1>
        <p v-if="store.scope" class="text-body-2 text-medium-emphasis">
          {{ store.scope.all ? 'Everyone in the organisation.' : 'Your direct reports.' }}
        </p>
      </div>
      <div class="d-flex align-center ga-3">
        <AppPillToggle v-model="store.report" :options="REPORTS" />
        <v-btn
          color="primary"
          variant="tonal"
          prepend-icon="mdi-download"
          :loading="store.exporting"
          :disabled="store.noAccess"
          @click="exportCsv"
        >
          Export CSV
        </v-btn>
      </div>
    </div>

    <div v-if="store.noAccess" class="empty">
      <v-icon icon="mdi-file-chart-outline" size="32" color="primary" />
      <div class="text-body-1 font-weight-medium mt-2">No reports for you yet</div>
      <div class="text-body-2 text-medium-emphasis">
        Leave reports show the leave of the people who report to you, or everyone's for HR.
      </div>
    </div>
    <template v-else>
      <ReportFilterBar class="mb-4" />
      <AppCallout v-if="store.scopeError" variant="error" class="mb-4">
        {{ store.scopeError }} Reload the page to pick people, offices or policies.
      </AppCallout>
      <AppCallout v-if="store.error || exportError" variant="error" class="mb-4">
        {{ exportError || store.error }}
      </AppCallout>
      <v-card color="surface" rounded="lg">
        <v-progress-linear v-if="store.loading" indeterminate color="primary" />
        <ReportSummaryTable v-if="store.report === 'summary'" :report="store.summary" />
        <ReportRegisterTable v-else-if="store.report === 'register'" :report="store.register" />
        <ReportBalancesTable v-else :report="store.balances" />
      </v-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import ReportBalancesTable from '@/components/leave/reports/ReportBalancesTable.vue'
import ReportFilterBar from '@/components/leave/reports/ReportFilterBar.vue'
import ReportRegisterTable from '@/components/leave/reports/ReportRegisterTable.vue'
import ReportSummaryTable from '@/components/leave/reports/ReportSummaryTable.vue'
import { useDebounced } from '@/composables/useDebounced'
import { useLeaveReportsStore } from '@/stores/leaveReports'
import type { ReportName } from '@/types/leaveReports'

const REPORTS: { label: string; value: ReportName }[] = [
  { label: 'Summary', value: 'summary' },
  { label: 'Requests', value: 'register' },
  { label: 'Balances', value: 'balances' },
]

const store = useLeaveReportsStore()
const exportError = ref('')

// Typing a custom date or picking several filters sends one request, not many.
const query = ref('')
const settled = useDebounced(query)
watch(
  () => [store.report, JSON.stringify(store.filters)],
  ([report, filters]) => {
    query.value = `${report}|${filters}`
  },
)
watch(settled, () => {
  exportError.value = ''
  if (!store.noAccess) void store.fetch()
})

async function exportCsv(): Promise<void> {
  exportError.value = (await store.exportCsv()) ?? ''
}

onMounted(async () => {
  await store.loadScope()
  if (!store.noAccess) await store.fetch()
})
</script>

<style scoped>
.reports {
  max-width: 1400px;
}
.empty {
  text-align: center;
  padding: 48px 16px;
}
</style>
