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

<!-- One of the caller's requests: a date badge, what and when, who decides
     (or decided, with their note on a rejection), the status, and a menu to
     cancel while that's still allowed. -->
<template>
  <li class="req">
    <span class="req__badge" aria-hidden="true">
      <span class="req__month">{{ badge.month }}</span>
      <span class="req__day">{{ badge.day }}</span>
    </span>
    <span class="req__text">
      <span class="req__kind">{{ requestTypeLabel(row) }}</span>
      <span class="req__meta">{{ when }}</span>
      <span v-if="lop" class="req__meta req__lop">{{ lop }}</span>
      <span v-if="approver" class="req__meta">{{ approver }}</span>
      <span v-if="row.status === 'rejected' && row.decision_note" class="req__meta">
        “{{ row.decision_note }}”
      </span>
    </span>
    <LeaveStatusChip :status="row.status" class="req__status" />
    <v-menu v-if="row.can_cancel" location="bottom end">
      <template #activator="{ props: menu }">
        <v-btn
          v-bind="menu"
          icon="mdi-dots-horizontal"
          variant="text"
          size="small"
          class="req__menu"
          :aria-label="`Options for ${requestTypeLabel(row)}, ${when}`"
        />
      </template>
      <v-list density="compact">
        <v-list-item title="Cancel request" @click="emit('cancel', row)" />
      </v-list>
    </v-menu>
  </li>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import LeaveStatusChip from '@/components/leave/LeaveStatusChip.vue'
import type { LeaveRequestRead } from '@/types/leave'
import { lopLabel, requestLength, requestTypeLabel, STATUS_META } from '@/utils/leave'
import { formatDayRange } from '@/utils/leaveDates'
import { dateBadge } from '@/utils/leaveHome'

const props = defineProps<{ row: LeaveRequestRead; pendingWith: string }>()
const emit = defineEmits<(e: 'cancel', row: LeaveRequestRead) => void>()

const badge = computed(() => dateBadge(props.row.start_date))
const lop = computed(() => lopLabel(props.row.lop_days))

const when = computed(() => `${formatDayRange(props.row.start_date, props.row.end_date)} · ${requestLength(props.row)}`)

const approver = computed(() => {
  const row = props.row
  if (row.approval_mode === 'auto_policy') return 'Approved automatically'
  if (row.status === 'pending') return props.pendingWith
  // A cancelled request keeps its approver, so don't say who cancelled it.
  if (row.decided_by && row.status !== 'cancelled') return `${STATUS_META[row.status].label} by ${row.decided_by.name}`
  return ''
})
</script>

<style scoped>
.req {
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr) auto 36px;
  grid-template-areas: 'badge text status menu';
  align-items: center;
  gap: 16px;
  padding: 14px 20px;
  border-top: 1px solid rgb(var(--v-theme-rule));
}
.req__menu {
  grid-area: menu;
}
.req__status {
  grid-area: status;
}
.req__badge {
  grid-area: badge;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 6px 0;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 10px;
}
.req__month {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  color: rgb(var(--v-theme-on-surface-variant));
}
.req__day {
  font-size: 20px;
  line-height: 24px;
  font-weight: 600;
}
.req__text {
  grid-area: text;
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex-grow: 1;
  min-width: 0;
}
.req__kind {
  font-size: var(--text-sm);
  font-weight: 500;
}
.req__meta {
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.req__lop {
  color: rgb(var(--v-theme-warning));
}
@media (max-width: 600px) {
  .req {
    grid-template-columns: 52px minmax(0, 1fr) 36px;
    grid-template-areas:
      'badge text menu'
      'badge status menu';
    gap: 6px 12px;
    padding: 12px 16px;
  }
  .req__status {
    justify-self: start;
  }
}
</style>
