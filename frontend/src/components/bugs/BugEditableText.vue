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

<!-- Text that editors can change in place: the value with an Edit button,
     which swaps it for a labelled field with Save and Cancel. The field
     stays open, with the draft, until ``save`` reports success. -->
<template>
  <div class="bug-text">
    <template v-if="editing">
      <v-textarea
        v-if="multiline"
        v-model="draft"
        :label="label"
        rows="4"
        auto-grow
        variant="outlined"
        density="compact"
        hide-details
        autofocus
      />
      <v-text-field v-else v-model="draft" :label="label" variant="outlined" density="compact" hide-details autofocus @keyup.enter="submit" />
      <div class="bug-text__actions">
        <v-btn variant="text" size="small" @click="editing = false">Cancel</v-btn>
        <v-btn variant="outlined" size="small" :loading="saving" :disabled="required && !draft.trim()" @click="submit">Save</v-btn>
      </div>
    </template>
    <div v-else class="bug-text__row">
      <p class="bug-text__value" :class="{ 'bug-text__value--empty': !value }">{{ value || emptyText }}</p>
      <v-btn
        v-if="editable"
        icon="mdi-pencil-outline"
        variant="text"
        size="x-small"
        :aria-label="`Edit ${label.toLowerCase()}`"
        @click="start"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = withDefaults(
  defineProps<{
    value: string
    label: string
    editable: boolean
    save: (value: string) => Promise<boolean>
    multiline?: boolean
    required?: boolean
    emptyText?: string
  }>(),
  { multiline: false, required: false, emptyText: '' },
)

const editing = ref(false)
const saving = ref(false)
const draft = ref('')

function start(): void {
  draft.value = props.value
  editing.value = true
}

async function submit(): Promise<void> {
  const value = props.multiline ? draft.value : draft.value.trim()
  if (saving.value || (props.required && !value.trim())) return
  saving.value = true
  const ok = await props.save(value)
  saving.value = false
  if (ok) editing.value = false
}
</script>

<style scoped>
.bug-text__row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.bug-text__value {
  flex: 1 1 auto;
  min-width: 0;
  margin: 0;
  font-size: 14px;
  line-height: 21px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.bug-text__value--empty {
  color: rgb(var(--v-theme-on-surface-variant));
}
.bug-text__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}
</style>
