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

<!-- Create a leave policy: where it applies, working days and when the
     leave year starts. Types and holidays are added after. -->
<template>
  <v-dialog :model-value="modelValue" max-width="560" @update:model-value="emit('update:modelValue', $event)">
    <v-card class="pa-0">
      <div class="d-flex align-center justify-space-between pa-6 pb-2">
        <h2 class="text-h6 font-weight-bold">Add policy</h2>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="close" />
      </div>
      <v-form class="px-6 d-flex flex-column ga-3" @submit.prevent="submit">
        <v-text-field v-model="draft.name" label="Name" autofocus v-bind="field" />
        <RegionFields v-model:country="draft.country_code" v-model:subdivision="draft.subdivision_code" />
        <div class="form-grid">
          <v-text-field v-model="draft.timezone" label="Timezone" hint="An IANA name, such as Europe/London." persistent-hint v-bind="field" />
          <v-select v-model="draft.year_start_month" :items="MONTH_ITEMS" label="Leave year starts in" v-bind="field" />
        </div>
        <WorkingDayChips v-model="draft.working_days" />
        <AppCallout v-if="error" variant="error">{{ error }}</AppCallout>
      </v-form>
      <div class="d-flex justify-end ga-2 pa-6 pt-4">
        <v-btn variant="text" @click="close">Cancel</v-btn>
        <v-btn color="primary" :loading="saving" :disabled="!draft.name.trim()" @click="submit">Create policy</v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import RegionFields from '@/components/leave/settings/RegionFields.vue'
import WorkingDayChips from '@/components/leave/settings/WorkingDayChips.vue'
import { useLeavePoliciesStore } from '@/stores/leavePolicies'
import type { PolicyRead, PolicyWrite } from '@/types/leavePolicy'
import { MONTH_ITEMS, newPolicy } from '@/utils/leavePolicy'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; created: [policy: PolicyRead] }>()

const store = useLeavePoliciesStore()
const field = { variant: 'outlined', density: 'compact', hideDetails: 'auto' } as const
const draft = ref<PolicyWrite>(newPolicy())
const saving = ref(false)
const error = ref('')

watch(
  () => props.modelValue,
  open => {
    if (!open) return
    draft.value = newPolicy()
    error.value = ''
  },
)

function close(): void {
  emit('update:modelValue', false)
}

async function submit(): Promise<void> {
  if (!draft.value.name.trim()) return
  saving.value = true
  const result = await store.createPolicy({ ...draft.value, name: draft.value.name.trim() })
  saving.value = false
  if (typeof result === 'string') {
    error.value = result
    return
  }
  emit('created', result)
  close()
}
</script>

<style scoped>
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
</style>
