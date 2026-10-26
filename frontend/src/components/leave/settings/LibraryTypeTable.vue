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

<!-- The library's types as a table, with the policies using each; a row opens it. -->
<template>
  <v-table density="comfortable" hover class="library">
    <thead>
      <tr>
        <th scope="col">Leave type</th>
        <th scope="col">Default allowance</th>
        <th scope="col">Policies</th>
        <th scope="col"><span class="d-sr-only">Edit</span></th>
      </tr>
    </thead>
    <tbody>
      <tr
        v-for="entry in entries"
        :key="entry.id"
        class="library__row"
        tabindex="0"
        :aria-label="`Edit ${entry.name}`"
        @click="emit('edit', entry)"
        @keydown.enter.prevent="emit('edit', entry)"
        @keydown.space.prevent="emit('edit', entry)"
      >
        <td>
          <span class="dot" aria-hidden="true" :style="{ background: `rgb(var(--v-theme-${swatchColor(entry.color_key)}))` }" />
          <span class="font-weight-medium">{{ entry.name }}</span>
          <div v-if="typeRuleTags(entry).length" class="tags">
            <v-chip v-for="tag in typeRuleTags(entry)" :key="tag" size="x-small" variant="outlined" label>{{ tag }}</v-chip>
          </div>
        </td>
        <td>{{ allowanceLabel(entry) }}</td>
        <td>
          <div class="text-body-2">{{ usesLabel(entry.uses) }}</div>
          <div v-if="entry.uses.length" class="tags tags--flush">
            <v-chip v-for="use in entry.uses" :key="use.type_id" size="x-small" variant="tonal" label>{{ useLabel(use) }}</v-chip>
          </div>
        </td>
        <td class="text-right">
          <v-icon icon="mdi-chevron-right" size="20" class="text-medium-emphasis" aria-hidden="true" />
        </td>
      </tr>
    </tbody>
  </v-table>
</template>

<script setup lang="ts">
import type { LibraryTypeRead } from '@/types/leaveLibrary'
import { swatchColor } from '@/utils/leave'
import { useLabel, usesLabel } from '@/utils/leaveLibrary'
import { allowanceLabel, typeRuleTags } from '@/utils/leavePolicyDisplay'

defineProps<{ entries: LibraryTypeRead[] }>()
const emit = defineEmits<{ edit: [entry: LibraryTypeRead] }>()
</script>

<style scoped>
.library {
  background: transparent;
}
.library__row {
  cursor: pointer;
}
.library__row:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: 4px 0 2px 20px;
}
.tags--flush {
  margin-left: 0;
}
.dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 10px;
}
</style>
