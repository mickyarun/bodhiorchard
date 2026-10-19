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

<!-- A policy's leave types. -->
<template>
  <section>
    <div class="d-flex justify-end mb-3">
      <v-btn color="primary" variant="tonal" size="small" prepend-icon="mdi-plus" @click="edit(null)">
        Add leave type
      </v-btn>
    </div>
    <AppCallout v-if="store.typesError" variant="error" class="mb-3">{{ store.typesError }}</AppCallout>
    <p v-if="!store.types.length && !store.typesError" class="text-body-2 text-medium-emphasis">
      No leave types yet. Add casual, sick or any other leave people can request.
    </p>
    <v-table v-else density="comfortable" hover>
      <thead>
        <tr>
          <th>Name</th>
          <th>Code</th>
          <th>Days a year</th>
          <th>Paid</th>
          <th>Status</th>
          <th />
        </tr>
      </thead>
      <tbody>
        <tr v-for="type in store.types" :key="type.id" :class="{ 'inactive': !type.is_active }">
          <td>
            <span class="dot" :style="{ background: `rgb(var(--v-theme-${swatchColor(type.color_key)}))` }" />
            {{ type.name }}
          </td>
          <td class="bo-mono">{{ type.code }}</td>
          <td>{{ quotaLabel(type) }}</td>
          <td>{{ type.is_paid ? 'Paid' : 'Unpaid' }}</td>
          <td>{{ type.is_active ? 'Active' : 'Off' }}</td>
          <td class="text-right">
            <v-btn icon="mdi-pencil-outline" variant="text" size="small" :aria-label="`Edit ${type.name}`" @click="edit(type)" />
          </td>
        </tr>
      </tbody>
    </v-table>
    <LeaveTypeDialog v-model="dialogOpen" :policy-id="policyId" :type="editing" />
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import LeaveTypeDialog from '@/components/leave/settings/LeaveTypeDialog.vue'
import { useLeavePolicyConfigStore } from '@/stores/leavePolicyConfig'
import type { LeaveTypeRead } from '@/types/leavePolicy'
import { formatDays, swatchColor, toNumberOrNull } from '@/utils/leave'

const props = defineProps<{ policyId: string }>()

const store = useLeavePolicyConfigStore()
const dialogOpen = ref(false)
const editing = ref<LeaveTypeRead | null>(null)

function quotaLabel(type: LeaveTypeRead): string {
  const quota = toNumberOrNull(type.annual_quota_days)
  return quota === null ? 'No limit' : formatDays(quota)
}

function edit(type: LeaveTypeRead | null): void {
  editing.value = type
  dialogOpen.value = true
}

watch(() => props.policyId, id => void store.fetchTypes(id), { immediate: true })
</script>

<style scoped>
.dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 8px;
}
.inactive {
  opacity: 0.55;
}
</style>
