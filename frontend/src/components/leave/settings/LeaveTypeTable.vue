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

<!-- Leave types as a table; a row opens it for editing. -->
<template>
  <v-table density="comfortable" hover class="leave-types">
    <thead>
      <tr>
        <th scope="col">Leave type</th>
        <th scope="col">Allowance</th>
        <th scope="col">Paid</th>
        <th scope="col"><span class="d-sr-only">Edit</span></th>
      </tr>
    </thead>
    <tbody>
      <tr
        v-for="type in types"
        :key="type.id"
        class="leave-types__row"
        :class="{ 'leave-types__row--off': !type.is_active }"
        tabindex="0"
        :aria-label="`Edit ${type.name}`"
        @click="emit('edit', type)"
        @keydown.enter.prevent="emit('edit', type)"
        @keydown.space.prevent="emit('edit', type)"
      >
        <td>
          <span class="dot" aria-hidden="true" :style="{ background: `rgb(var(--v-theme-${swatchColor(type.color_key)}))` }" />
          <span class="font-weight-medium">{{ type.name }}</span>
          <v-chip v-if="!type.is_active" size="x-small" variant="tonal" label class="ml-2">Off</v-chip>
          <div v-if="typeRuleTags(type).length" class="tags">
            <v-chip v-for="tag in typeRuleTags(type)" :key="tag" size="x-small" variant="outlined" label>{{ tag }}</v-chip>
          </div>
        </td>
        <td>{{ allowanceLabel(type) }}</td>
        <td>
          <v-chip size="small" variant="tonal" :color="type.is_paid ? 'success' : undefined" label>
            {{ type.is_paid ? 'Paid' : 'Unpaid' }}
          </v-chip>
        </td>
        <td class="text-right">
          <v-icon icon="mdi-chevron-right" size="20" class="text-medium-emphasis" aria-hidden="true" />
        </td>
      </tr>
    </tbody>
  </v-table>
</template>

<script setup lang="ts">
import type { LeaveTypeRead } from '@/types/leavePolicy'
import { swatchColor } from '@/utils/leave'
import { allowanceLabel, typeRuleTags } from '@/utils/leavePolicyDisplay'

defineProps<{ types: LeaveTypeRead[] }>()
const emit = defineEmits<{ edit: [type: LeaveTypeRead] }>()
</script>

<style scoped>
.leave-types {
  background: transparent;
}
.leave-types__row {
  cursor: pointer;
}
.leave-types__row:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.leave-types__row--off td:not(:last-child) {
  opacity: 0.6;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: 4px 0 2px 20px;
}
.dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 10px;
}
</style>
