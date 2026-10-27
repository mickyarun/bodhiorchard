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

<!-- Needs your attention: BUDs waiting on a person, plus the approver's
     leave queue as one row. Each row has a single next-step button. -->
<template>
  <AppPanel title="Needs your attention" :note="countLabel" flush>
    <ul v-if="total" class="attention">
      <li v-for="item in attention.items" :key="item.key" class="attention__row">
        <span class="attention__ref">{{ item.ref }}</span>
        <BudPriorityChip :priority="item.priority" />
        <span class="attention__text">
          <span class="attention__title">{{ item.title }}</span>
          <span class="attention__meta">{{ item.meta }}</span>
        </span>
        <v-btn variant="outlined" size="small" :to="item.to" class="attention__btn">
          {{ item.action }}<span class="d-sr-only"> {{ item.ref }}</span>
        </v-btn>
      </li>
      <li v-if="pendingLeave" class="attention__row">
        <span class="attention__ref">Leave</span>
        <span class="attention__text">
          <span class="attention__title">{{ leaveTitle }}</span>
          <span class="attention__meta">Waiting for your approval</span>
        </span>
        <v-btn variant="outlined" size="small" to="/leave/approvals" class="attention__btn">Approve</v-btn>
      </li>
    </ul>
    <p v-else class="attention__empty">Nothing is waiting on anyone right now.</p>
  </AppPanel>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppPanel from '@/components/common/AppPanel.vue'
import BudPriorityChip from '@/components/buds/BudPriorityChip.vue'
import type { AttentionList } from '@/utils/dashboardOverview'

const props = defineProps<{
  attention: AttentionList
  pendingLeave: number | null
}>()

const total = computed(() => props.attention.total + (props.pendingLeave ? 1 : 0))
const countLabel = computed(() => (total.value === 1 ? '1 item' : `${total.value} items`))
const leaveTitle = computed(() =>
  props.pendingLeave === 1 ? '1 leave request waiting' : `${props.pendingLeave} leave requests waiting`,
)
</script>

<style scoped>
.attention {
  list-style: none;
  margin: 0;
  padding: 0;
}
.attention__row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  border-top: 1px solid rgb(var(--v-theme-rule));
}
.attention__ref {
  width: 64px;
  flex-shrink: 0;
  font: 500 12px var(--font-mono);
  color: rgb(var(--v-theme-on-surface-variant));
}
.attention__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex-grow: 1;
  min-width: 0;
}
.attention__title {
  font-size: var(--text-sm);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.attention__meta {
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.attention__btn {
  flex-shrink: 0;
}
.attention__empty {
  margin: 0;
  padding: 0 20px 18px;
  font-size: var(--text-sm);
  color: rgb(var(--v-theme-on-surface-variant));
}
@media (max-width: 600px) {
  .attention__row {
    flex-wrap: wrap;
    gap: 8px 12px;
    padding: 12px 16px;
  }
  .attention__ref {
    width: auto;
  }
  .attention__text {
    flex-basis: 100%;
    order: 3;
  }
  .attention__btn {
    margin-left: auto;
  }
  .attention__title {
    white-space: normal;
  }
}
</style>
