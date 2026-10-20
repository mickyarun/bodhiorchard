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

<!-- A glance at this leave year in the request dialog: used and pending per
     type (the type picker already says what's left), loss of pay so far,
     and WFH days left without approval this month. -->
<template>
  <div v-if="kind === 'leave' && summary.balances.length" class="strip">
    <div class="text-caption text-medium-emphasis mb-1">This leave year · {{ formatLeaveYear(summary.leave_year) }}</div>
    <div class="d-flex flex-wrap ga-2">
      <v-chip
        v-for="b in summary.balances"
        :key="b.leave_type.id"
        size="small"
        :variant="b.leave_type.id === selectedTypeId ? 'flat' : 'tonal'"
        :color="b.leave_type.id === selectedTypeId ? 'primary' : undefined"
        label
      >
        {{ balanceChipLabel(b) }}
      </v-chip>
      <v-chip v-if="lop" size="small" color="warning" variant="tonal" label>
        Loss of pay so far: {{ formatDays(lop) }}
      </v-chip>
    </div>
  </div>
  <div v-else-if="kind === 'wfh' && wfhLine" class="text-caption text-medium-emphasis">
    {{ wfhLine }}
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { LeaveKind, LeaveSummary } from '@/types/leave'
import { formatDays, toNumber } from '@/utils/leave'
import { balanceChipLabel, wfhAllowanceLine } from '@/utils/leaveBalanceStrip'
import { formatLeaveYear } from '@/utils/leaveDates'

const props = defineProps<{ summary: LeaveSummary; kind: LeaveKind; selectedTypeId: string | null }>()

const lop = computed(() => toNumber(props.summary.lop_days))
const wfhLine = computed(() => wfhAllowanceLine(props.summary.wfh_auto_days_left_this_month))
</script>

<style scoped>
.strip {
  margin-top: -4px;
}
</style>
