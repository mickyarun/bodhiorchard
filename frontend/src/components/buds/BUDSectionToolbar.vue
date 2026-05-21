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

<script setup lang="ts">
import { ref } from 'vue'
import PhaseLockedBtn from './PhaseLockedBtn.vue'

const props = withDefaults(
  defineProps<{
    isEditing: boolean
    agentLocked: boolean
    activeTab: string
    currentSection: string
    // True only when the BUD's status matches the section's owning phase.
    // When false, the Edit / Import buttons disable and explain why via tooltip.
    editable?: boolean
    editLockTooltip?: string
  }>(),
  { editable: true, editLockTooltip: '' },
)

const emit = defineEmits<{
  'toggle-edit': []
  'export-section': [section: string]
  'import-section': [section: string, file: File]
  'open-history': [section: string]
}>()

const fileInput = ref<HTMLInputElement | null>(null)
// Snapshot the section at click-time so the file-picker callback
// resolves against the section the user actually targeted, even if
// they navigate to another tab while the OS dialog is open.
const pendingSection = ref('')

function pickFile(): void {
  pendingSection.value = props.currentSection
  fileInput.value?.click()
}

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) emit('import-section', pendingSection.value, file)
  // Reset so re-uploading the same file fires the change event again.
  input.value = ''
}
</script>

<template>
  <div class="toolbar-actions">
    <PhaseLockedBtn
      :disabled="agentLocked || !editable"
      :tooltip="props.editLockTooltip"
      :tooltip-disabled="editable || agentLocked"
      @click="emit('toggle-edit')"
    >
      <v-icon size="15" class="mr-1">
        {{ isEditing ? 'mdi-eye-outline' : 'mdi-pencil-outline' }}
      </v-icon>
      {{ isEditing ? 'Preview' : 'Edit' }}
    </PhaseLockedBtn>
    <span class="toolbar-sep" />
    <v-btn
      variant="text"
      size="small"
      class="toolbar-btn"
      title="View version history and restore previous edits"
      @click="emit('open-history', currentSection)"
    >
      <v-icon size="15" class="mr-1">mdi-history</v-icon>
      History
    </v-btn>
    <span class="toolbar-sep" />
    <v-btn
      variant="text"
      size="small"
      class="toolbar-btn"
      :disabled="agentLocked"
      @click="emit('export-section', currentSection)"
    >
      <v-icon size="15" class="mr-1">mdi-tray-arrow-down</v-icon>
      Export
    </v-btn>
    <PhaseLockedBtn
      v-if="activeTab !== 'design'"
      :disabled="agentLocked || !editable"
      :tooltip="props.editLockTooltip"
      :tooltip-disabled="editable || agentLocked"
      @click="pickFile"
    >
      <v-icon size="15" class="mr-1">mdi-tray-arrow-up</v-icon>
      Import
    </PhaseLockedBtn>
    <input
      ref="fileInput"
      type="file"
      accept=".md,.txt,.markdown,.html,.htm"
      style="display: none;"
      @change="onFileChange"
    />
  </div>
</template>

<style scoped>
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-right: 4px;
}

.toolbar-actions .v-btn {
  text-transform: none;
  letter-spacing: 0;
  font-weight: 500;
  font-size: 12px;
}

.toolbar-sep {
  width: 1px;
  height: 18px;
  background: rgba(var(--v-theme-on-surface), 0.12);
}
</style>
