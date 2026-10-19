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

<!-- Change bank, ID and address details. Blank fields are left as they are;
     the employee is told whenever bank or ID details change. -->
<template>
  <v-dialog :model-value="modelValue" max-width="640" :fullscreen="xs" @update:model-value="close">
    <v-card class="pa-0">
      <div class="d-flex align-center justify-space-between pa-6 pb-2">
        <div>
          <h2 class="text-h6 font-weight-bold">Edit bank &amp; IDs</h2>
          <p class="text-caption text-medium-emphasis">
            Leave a field blank to keep what's saved. Saved values aren't shown here.
          </p>
        </div>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="close" />
      </div>
      <v-form class="px-6" @submit.prevent="submit">
        <div v-for="group in GROUPS" :key="group.title" class="mb-4">
          <div class="text-overline text-medium-emphasis mb-2">{{ group.title }}</div>
          <div class="form-grid">
            <v-text-field
              v-for="field in group.fields"
              :key="field.key"
              v-model="draft[field.key]"
              :label="field.label"
              :placeholder="field.placeholder"
              :class="{ 'span-2': field.wide }"
              autocomplete="off"
              v-bind="input"
            />
          </div>
        </div>
        <AppCallout v-if="error" variant="error" class="mb-2">{{ error }}</AppCallout>
      </v-form>
      <v-divider />
      <div class="d-flex justify-end ga-2 pa-4">
        <v-btn variant="text" @click="close">Cancel</v-btn>
        <v-btn color="primary" :loading="saving" :disabled="!changed" @click="submit">Save changes</v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import AppCallout from '@/components/common/AppCallout.vue'
import type { SensitiveWrite } from '@/types/employeeRecords'

type Key = keyof SensitiveWrite
interface FieldDef {
  key: Key
  label: string
  placeholder?: string
  wide?: boolean
}

const GROUPS: { title: string; fields: FieldDef[] }[] = [
  {
    title: 'Bank',
    fields: [
      { key: 'bank_name', label: 'Bank name' },
      { key: 'bank_ifsc', label: 'IFSC', placeholder: 'HDFC0001234' },
      { key: 'bank_account_number', label: 'Account number', wide: true },
    ],
  },
  {
    title: 'IDs',
    fields: [
      { key: 'pan', label: 'PAN', placeholder: 'ABCDE1234F' },
      { key: 'aadhaar', label: 'Aadhaar', placeholder: '1234 5678 9012' },
      { key: 'passport_number', label: 'Passport number' },
    ],
  },
  {
    title: 'Addresses',
    fields: [
      { key: 'current_address', label: 'Current address', wide: true },
      { key: 'permanent_address', label: 'Permanent address', wide: true },
    ],
  },
]

const props = defineProps<{ modelValue: boolean; save: (body: SensitiveWrite) => Promise<string | null> }>()
const emit = defineEmits<(e: 'update:modelValue', value: boolean) => void>()
const { xs } = useDisplay()
const input = { variant: 'outlined', density: 'comfortable', hideDetails: 'auto' } as const
const draft = ref<SensitiveWrite>({})
const saving = ref(false)
const error = ref('')

// Only fields someone typed into are sent, so nothing saved is overwritten.
const changes = computed<SensitiveWrite>(() =>
  Object.fromEntries(Object.entries(draft.value).filter(([, v]) => typeof v === 'string' && v.trim())),
)
const changed = computed(() => Object.keys(changes.value).length > 0)

watch(
  () => props.modelValue,
  open => {
    if (open) {
      draft.value = {}
      error.value = ''
    }
  },
)

function close(): void {
  emit('update:modelValue', false)
}

async function submit(): Promise<void> {
  if (!changed.value) return
  saving.value = true
  error.value = (await props.save(changes.value)) ?? ''
  saving.value = false
  if (!error.value) close()
}
</script>

<style scoped>
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.span-2 {
  grid-column: 1 / -1;
}
@media (max-width: 600px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
