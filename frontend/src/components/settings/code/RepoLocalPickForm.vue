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

<!--
  Local-pick body of the Add dialog. Owns just the picker invocation
  and the staged-paths list. Submit + cancel live in the dialog footer
  (single source of truth) — this form is purely presentational.
-->
<template>
  <div>
    <div class="d-flex align-center ga-3 mb-3">
      <div class="flex-grow-1 min-w-0">
        <div class="text-body-2 font-weight-medium">Pick folders on this machine</div>
        <div class="text-caption text-medium-emphasis">
          Read in place — no copying or git fetch.
        </div>
      </div>
      <v-btn
        prepend-icon="mdi-folder-plus-outline"
        variant="tonal"
        color="primary"
        size="small"
        class="text-none"
        :disabled="imp.running.value"
        @click="openPicker"
      >
        Choose folders
      </v-btn>
    </div>

    <div
      v-if="imp.localPaths.value.length === 0"
      class="empty-line text-caption text-medium-emphasis"
    >
      <v-icon icon="mdi-folder-outline" size="14" class="mr-1" />
      No folders staged yet.
    </div>

    <div v-else class="d-flex flex-column ga-1">
      <div
        v-for="(item, idx) in imp.localPaths.value"
        :key="item.source"
        class="path-row d-flex align-center ga-2 px-2 py-1 rounded"
      >
        <v-icon
          :icon="iconFor(item.status)"
          :color="colorFor(item.status)"
          size="16"
          class="flex-grow-0 flex-shrink-0"
        />
        <div class="flex-grow-1 min-w-0">
          <div class="text-body-2 text-truncate">{{ item.source }}</div>
          <div v-if="item.error" class="text-caption text-error text-truncate">
            {{ item.error }}
          </div>
        </div>
        <v-btn
          icon="mdi-close"
          size="x-small"
          variant="text"
          density="compact"
          :disabled="item.status === 'running'"
          @click="imp.removeLocalPath(idx)"
        />
      </div>
    </div>

    <DirectoryPicker
      ref="picker"
      multi-select
      @select="imp.addLocalPath"
      @select-multiple="imp.addLocalPaths"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import DirectoryPicker from '@/components/setup/DirectoryPicker.vue'
import type { useRepoImport, ImportItemStatus } from '@/composables/useRepoImport'

defineProps<{
  imp: ReturnType<typeof useRepoImport>
}>()

const picker = ref<InstanceType<typeof DirectoryPicker> | null>(null)

function openPicker(): void {
  picker.value?.open()
}

function iconFor(status: ImportItemStatus): string {
  return status === 'done'
    ? 'mdi-check-circle'
    : status === 'error'
      ? 'mdi-alert-circle-outline'
      : status === 'running'
        ? 'mdi-progress-clock'
        : 'mdi-folder-outline'
}

function colorFor(status: ImportItemStatus): string {
  return status === 'done'
    ? 'success'
    : status === 'error'
      ? 'error'
      : status === 'running'
        ? 'primary'
        : 'medium-emphasis'
}
</script>

<style scoped>
.empty-line {
  display: flex;
  align-items: center;
  padding: 12px;
  background: rgba(var(--v-theme-on-surface), 0.02);
  border: 1px dashed rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 6px;
}

.path-row {
  background: rgba(var(--v-theme-on-surface), 0.03);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}
</style>
