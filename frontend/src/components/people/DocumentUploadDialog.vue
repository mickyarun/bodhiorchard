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

<!-- Upload one document: pick its type, choose the file. -->
<template>
  <v-dialog :model-value="modelValue" max-width="520" @update:model-value="close">
    <v-card class="pa-0">
      <div class="d-flex align-center justify-space-between pa-6 pb-2">
        <h2 class="text-h6 font-weight-bold">Upload document</h2>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="close" />
      </div>
      <div class="px-6 d-flex flex-column ga-4">
        <v-select v-model="docType" :items="TYPES" label="Type" v-bind="input" />
        <v-file-input
          v-model="file"
          label="File"
          accept=".pdf,.jpg,.jpeg,.png"
          prepend-icon=""
          prepend-inner-icon="mdi-paperclip"
          show-size
          v-bind="input"
        />
        <AppCallout v-if="error" variant="error">{{ error }}</AppCallout>
      </div>
      <div class="d-flex justify-end ga-2 pa-6 pt-4">
        <v-btn variant="text" @click="close">Cancel</v-btn>
        <v-btn color="primary" :loading="saving" :disabled="!file" @click="submit">Upload</v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import type { DocumentType } from '@/types/employeeRecords'
import { selectItems } from '@/utils/employee'
import { DOC_TYPE_LABELS } from '@/utils/employeeRecords'

const props = defineProps<{
  modelValue: boolean
  upload: (docType: DocumentType, file: File) => Promise<string | null>
}>()
const emit = defineEmits<(e: 'update:modelValue', value: boolean) => void>()
const TYPES = selectItems<DocumentType>(DOC_TYPE_LABELS)
const input = { variant: 'outlined', density: 'comfortable', hideDetails: 'auto' } as const
const docType = ref<DocumentType>('id_proof')
const file = ref<File | null>(null)
const saving = ref(false)
const error = ref('')

watch(
  () => props.modelValue,
  open => {
    if (open) {
      file.value = null
      error.value = ''
    }
  },
)

function close(): void {
  emit('update:modelValue', false)
}

async function submit(): Promise<void> {
  if (!file.value) return
  saving.value = true
  error.value = (await props.upload(docType.value, file.value)) ?? ''
  saving.value = false
  if (!error.value) close()
}
</script>
