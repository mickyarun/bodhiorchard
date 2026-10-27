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
  <LeavePage title="Leave reports" :subtitle="subtitle">
    <template #actions>
      <AppPillToggle v-model="store.report" :options="REPORTS" aria-label="Report" />
      <v-btn
        variant="outlined"
        prepend-icon="mdi-download"
        :loading="store.exporting"
        :disabled="store.noAccess"
        @click="exportCsv"
      >
        Export CSV
      </v-btn>
    </template>

    <div v-if="store.noAccess" class="empty">
      <div class="empty__title">No reports for you yet</div>
      <div class="empty__text">
        Leave reports show the leave of the people who report to you, or everyone's for HR.
      </div>
    </div>
    <template v-else>
      <ReportFilterBar />
      <AppCallout v-if="store.scopeError" variant="error">
        {{ store.scopeError }} Reload the page to pick people, offices or policies.
      </AppCallout>
      <AppCallout v-if="store.error || exportError" variant="error">
        {{ exportError || store.error }}
      </AppCallout>
      <section class="report" :aria-label="REPORT_LABELS[store.report]">
        <v-progress-linear v-if="store.loading" indeterminate color="primary" />
        <ReportSummaryTable v-if="store.report === 'summary'" :report="store.summary" />
        <ReportRegisterTable v-else-if="store.report === 'register'" :report="store.register" />
        <ReportBalancesTable v-else :report="store.balances" />
      </section>
    </template>
  </LeavePage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import LeavePage from '@/components/leave/LeavePage.vue'
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

const REPORT_LABELS: Record<ReportName, string> = {
  summary: 'Leave taken by person',
  register: 'Every request',
  balances: 'Balances by person and type',
}

const store = useLeaveReportsStore()
const subtitle = computed(() => {
  if (!store.scope) return ''
  return store.scope.all ? 'Everyone in the organisation.' : 'Your direct reports.'
})
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
.report {
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
  overflow: hidden;
  min-width: 0;
}
.report :deep(.v-table) {
  background: transparent;
}
.report :deep(.v-table__wrapper > table > thead > tr > th) {
  background: rgb(var(--v-theme-background));
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface-variant));
  white-space: nowrap;
}
.report :deep(.v-table__wrapper > table > tbody) {
  font-variant-numeric: tabular-nums;
}
.empty {
  text-align: center;
  padding: 48px 16px;
}
.empty__title {
  font-size: var(--text-base);
  font-weight: 500;
}
.empty__text {
  font-size: var(--text-sm);
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
