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
import { ref, watch } from 'vue'
import { useDesignSystemStore, type DesignSystemItem } from '@/stores/designSystem'

const props = defineProps<{
  modelValue: boolean
  target: DesignSystemItem | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const dsStore = useDesignSystemStore()

const draft = ref('')
const saving = ref(false)
const errorText = ref('')

watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      draft.value = props.target?.custom_content ?? ''
      errorText.value = ''
    }
  },
)

function close(): void {
  emit('update:modelValue', false)
}

async function save(): Promise<void> {
  if (!props.target) return
  saving.value = true
  errorText.value = ''
  const ok = await dsStore.updateCustomContent(props.target.id, draft.value)
  saving.value = false
  if (ok) close()
  else errorText.value = dsStore.error ?? 'Failed to save customisations.'
}

async function reset(): Promise<void> {
  if (!props.target) return
  saving.value = true
  errorText.value = ''
  const ok = await dsStore.resetCustomisations(props.target.id)
  saving.value = false
  if (ok) close()
  else errorText.value = dsStore.error ?? 'Failed to reset customisations.'
}
</script>

<template>
  <v-dialog :model-value="modelValue" max-width="780" persistent @update:model-value="emit('update:modelValue', $event)">
    <v-card color="surface" class="pa-6">
      <div class="d-flex align-center mb-2">
        <span class="text-h6 flex-grow-1">
          Customise {{ target?.repo_name || 'Design System' }}
        </span>
        <v-btn icon="mdi-close" size="small" variant="text" @click="close" />
      </div>
      <div class="text-body-2 text-medium-emphasis mb-3">
        Markdown saved here is appended after the extracted content as
        <code>## User Customizations</code> and treated as the authoritative
        override layer by the Designer agent. The extracted content is owned
        by the scanner; <strong>this section is never overwritten by re-scans
        or PR merges</strong>.
      </div>
      <v-textarea
        v-model="draft"
        variant="outlined"
        rows="14"
        auto-grow
        hide-details
        placeholder="# Overrides

:root {
  --primary-500: #0066ff;   /* corrects the extracted token */
}

## Additional patterns

- ..."
        class="customise-editor"
      />
      <v-alert
        v-if="errorText"
        type="error"
        variant="tonal"
        class="mt-3"
        closable
        @click:close="errorText = ''"
      >
        {{ errorText }}
      </v-alert>
      <v-card-actions class="pa-0 mt-4">
        <v-btn
          v-if="target?.is_customised"
          variant="text"
          color="warning"
          :disabled="saving"
          @click="reset"
        >
          <v-icon start size="15">mdi-restore</v-icon>
          Reset to extracted
        </v-btn>
        <v-spacer />
        <v-btn variant="text" :disabled="saving" @click="close">Cancel</v-btn>
        <v-btn color="primary" variant="flat" :loading="saving" @click="save">Save</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.customise-editor :deep(textarea) {
  font-family: 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace;
  font-size: 12.5px;
  line-height: 1.55;
}
</style>
