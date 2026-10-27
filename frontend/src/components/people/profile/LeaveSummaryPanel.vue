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

<!-- "Leave this year" beside the profile: days left per leave type with a
     bar for the free share. Details opens the full Leave tab. -->
<template>
  <AppPanel title="Leave this year">
    <template #action>
      <v-btn variant="text" size="small" color="primary" @click="emit('details')">Details</v-btn>
    </template>
    <v-progress-linear v-if="balances.loading.value" indeterminate color="primary" />
    <p v-else-if="balances.error.value" class="leave-sum__empty">{{ balances.error.value }}</p>
    <p v-else-if="rows.length === 0" class="leave-sum__empty">No leave types on this policy yet.</p>
    <ul v-else class="leave-sum">
      <li v-for="row in rows" :key="row.key" class="leave-sum__row">
        <div class="leave-sum__line">
          <span class="leave-sum__name">{{ row.name }}</span>
          <span class="leave-sum__left">{{ row.left }}</span>
        </div>
        <div v-if="row.percent !== null" class="leave-sum__track" aria-hidden="true">
          <div class="leave-sum__fill" :style="{ width: `${row.percent}%`, background: `rgb(var(--v-theme-${row.color}))` }" />
        </div>
      </li>
    </ul>
  </AppPanel>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import AppPanel from '@/components/common/AppPanel.vue'
import { useMemberBalances } from '@/composables/useMemberBalances'
import { leaveSummary } from '@/utils/employeeProfile'

const props = defineProps<{ userId: string }>()
const emit = defineEmits<{ details: [] }>()

const balances = useMemberBalances()
const rows = computed(() => leaveSummary(balances.data.value?.balances ?? []))

watch(() => props.userId, id => void balances.load(id), { immediate: true })
</script>

<style scoped>
.leave-sum {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.leave-sum__row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.leave-sum__line {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}
.leave-sum__name {
  color: rgb(var(--v-theme-ink-2));
}
.leave-sum__left {
  font-weight: 600;
  white-space: nowrap;
}
.leave-sum__track {
  height: 6px;
  border-radius: var(--radius-pill);
  background: rgb(var(--v-theme-surface-variant));
  overflow: hidden;
}
.leave-sum__fill {
  height: 100%;
  border-radius: var(--radius-pill);
}
.leave-sum__empty {
  margin: 0;
  font-size: 14px;
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
