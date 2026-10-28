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

<!-- One request in the approvals list: who, what, when, how long ago it was
     sent, and a loss-of-pay warning. Selecting it opens it in the detail. -->
<template>
  <button
    type="button"
    class="queue-item"
    :class="{ 'queue-item--on': selected }"
    :aria-expanded="controls ? selected : undefined"
    :aria-controls="controls && selected ? controls : undefined"
    :aria-current="!controls && selected ? 'true' : undefined"
    @click="emit('select')"
  >
    <AppMonogram :name="request.user.name" :size="34" tone="brand" />
    <span class="queue-item__text">
      <span class="queue-item__top">
        <span class="queue-item__name">{{ request.user.name }}</span>
        <span class="queue-item__age">{{ age }}</span>
      </span>
      <span class="queue-item__what">{{ requestTypeLabel(request) }} · {{ length }}</span>
      <span class="queue-item__when">{{ formatDayRange(request.start_date, request.end_date) }}</span>
      <span v-if="lop" class="queue-item__warn">
        <v-icon icon="mdi-alert-outline" size="14" aria-hidden="true" />{{ lop }}
      </span>
      <LeaveStatusChip v-if="request.status !== 'pending'" :status="request.status" class="queue-item__status" />
    </span>
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppMonogram from '@/components/common/AppMonogram.vue'
import LeaveStatusChip from '@/components/leave/LeaveStatusChip.vue'
import type { ApprovalItem } from '@/types/leave'
import { timestampAgo } from '@/utils/approvalFacts'
import { lopLabel, requestLength, requestTypeLabel } from '@/utils/leave'
import { formatDayRange } from '@/utils/leaveDates'

const props = defineProps<{
  item: ApprovalItem
  selected: boolean
  /** On narrow screens the row opens the request below it: that card's id. */
  controls: string | null
}>()
const emit = defineEmits<(e: 'select') => void>()

const request = computed(() => props.item.request)
// Pending rows say when they were sent; decided ones when they were decided.
const age = computed(() => {
  const r = request.value
  if (r.status !== 'pending' && r.decided_at) return `Decided ${timestampAgo(r.decided_at, new Date())}`
  return `Sent ${timestampAgo(r.created_at, new Date())}`
})
const lop = computed(() => lopLabel(request.value.lop_days))
const length = computed(() => requestLength(request.value))
</script>

<style scoped>
.queue-item {
  appearance: none;
  border: none;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 16px;
  cursor: pointer;
}
.queue-item:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.queue-item:focus-visible {
  outline: 2px solid var(--color-focus);
  outline-offset: -2px;
}
.queue-item--on,
.queue-item--on:hover {
  background: rgba(var(--v-theme-primary), 0.06);
  box-shadow: inset 0 0 0 1px rgb(var(--v-theme-primary));
}
.queue-item__text {
  display: flex;
  flex-direction: column;
  gap: 3px;
  flex-grow: 1;
  min-width: 0;
}
.queue-item__top {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.queue-item__name {
  flex-grow: 1;
  font-size: var(--text-sm);
  font-weight: 600;
}
.queue-item__age {
  font-size: 12px;
  white-space: nowrap;
  color: rgb(var(--v-theme-on-surface-variant));
}
.queue-item__what {
  font-size: 13px;
  color: rgb(var(--v-theme-ink-2));
}
.queue-item__when {
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.queue-item__warn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
  color: rgb(var(--v-theme-warning));
}
.queue-item__status {
  align-self: flex-start;
  margin-top: 2px;
}
</style>
