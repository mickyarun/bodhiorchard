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

<!-- Profile Leave tab: the member's requests in a leave year, any status,
     with CSV export. No reasons: the same columns as the requests report. -->
<template>
  <section>
    <div class="d-flex align-center justify-space-between flex-wrap ga-3 mb-3">
      <h3 class="text-subtitle-2 font-weight-bold">Leave history</h3>
      <div class="d-flex align-center flex-wrap ga-3">
        <v-select v-model="year" :items="years" label="Leave year" v-bind="FIELD" />
        <v-select v-model="kind" :items="KIND_OPTIONS" label="Kind" clearable v-bind="FIELD" />
        <v-btn variant="tonal" size="small" prepend-icon="mdi-download" :loading="exporting" @click="exportCsv">
          Export CSV
        </v-btn>
      </div>
    </div>
    <AppCallout v-if="history.error.value || exportError" variant="error" class="mb-3">
      {{ exportError || history.error.value }}
    </AppCallout>
    <v-card color="surface" rounded="lg" variant="outlined">
      <v-progress-linear v-if="history.loading.value" indeterminate color="primary" />
      <ReportRegisterTable :report="history.data.value" :show-employee="false" />
    </v-card>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import ReportRegisterTable from '@/components/leave/reports/ReportRegisterTable.vue'
import { useMemberHistory } from '@/composables/useMemberHistory'
import type { LeaveKind } from '@/types/leave'
import { KIND_OPTIONS, leaveYearOptions } from '@/utils/leaveFilterOptions'

// currentYear: the member's current leave-year label, from their policy.
const props = defineProps<{ userId: string; currentYear: number }>()

const FIELD = { density: 'compact', variant: 'outlined', hideDetails: true, class: 'field' } as const
const years = computed(() => leaveYearOptions([props.currentYear]))

const history = useMemberHistory(() => props.userId)
const year = ref<number | null>(null)
const kind = ref<LeaveKind | null>(null)
const exporting = ref(false)
const exportError = ref('')

async function exportCsv(): Promise<void> {
  exporting.value = true
  exportError.value = (await history.exportCsv(year.value, kind.value)) ?? ''
  exporting.value = false
}

watch([() => props.userId, year, kind], () => void history.load(year.value, kind.value), { immediate: true })
</script>

<style scoped>
.field {
  min-width: 150px;
  max-width: 200px;
}
</style>
