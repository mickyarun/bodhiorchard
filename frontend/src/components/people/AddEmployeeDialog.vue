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

<!-- Create an employee record for an existing member. New hires are
     invited from Members first; this picks from members without a record. -->
<template>
  <v-dialog :model-value="modelValue" max-width="480" @update:model-value="emit('update:modelValue', $event)">
    <v-card class="pa-0">
      <div class="d-flex align-center justify-space-between pa-6 pb-2">
        <h2 class="text-h6 font-weight-bold">Add employee</h2>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="close" />
      </div>
      <v-form class="px-6" @submit.prevent="submit">
        <v-autocomplete
          v-model="userId"
          :items="store.candidates"
          item-title="name"
          item-value="user_id"
          label="Member"
          :loading="store.candidatesState === 'loading'"
          :hint="candidatesHint"
          persistent-hint
          v-bind="field"
        >
          <template #item="{ props: itemProps, item }">
            <v-list-item v-bind="itemProps" :subtitle="item.raw.email" />
          </template>
        </v-autocomplete>
        <div class="form-grid mt-3">
          <v-text-field v-model="work.designation" label="Designation" v-bind="field" />
          <v-text-field v-model="work.department" label="Department" v-bind="field" />
          <v-text-field v-model="work.date_of_joining" label="Date of joining" type="date" v-bind="field" />
          <v-select v-model="work.employment_type" :items="TYPES" label="Employment type" v-bind="field" />
        </div>
        <AppCallout v-if="error" variant="error" class="mt-3">{{ error }}</AppCallout>
      </v-form>
      <div class="d-flex justify-end ga-2 pa-6 pt-4">
        <v-btn variant="text" @click="close">Cancel</v-btn>
        <v-btn color="primary" :loading="saving" :disabled="!userId" @click="submit">Create record</v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppCallout from '@/components/common/AppCallout.vue'
import { useEmployeesStore } from '@/stores/employees'
import type { EmployeeWork } from '@/types/employee'
import { blankToNull, EMPLOYMENT_TYPE_LABELS, selectItems } from '@/utils/employee'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<(e: 'update:modelValue', value: boolean) => void>()

const store = useEmployeesStore()
const router = useRouter()
const TYPES = selectItems(EMPLOYMENT_TYPE_LABELS)
const field = { variant: 'outlined', density: 'compact', hideDetails: 'auto' } as const

const EMPTY: EmployeeWork = {
  employee_code: null,
  designation: null,
  department: null,
  employment_type: 'full_time',
  status: 'active',
  date_of_joining: null,
  date_of_exit: null,
  country_code: null,
  work_location: null,
}
const candidatesHint = computed(() => {
  if (store.candidatesState === 'error') return "Couldn't load members. Close and try again."
  if (store.candidatesState === 'loaded' && store.candidates.length === 0) {
    return 'Every member already has a record. Invite new hires from Members first.'
  }
  return ''
})
const userId = ref<string | null>(null)
const work = ref<EmployeeWork>({ ...EMPTY })
const saving = ref(false)
const error = ref('')

watch(
  () => props.modelValue,
  open => {
    if (!open) return
    userId.value = null
    work.value = { ...EMPTY }
    error.value = ''
    void store.fetchCandidates()
  },
)

function close(): void {
  emit('update:modelValue', false)
}

async function submit(): Promise<void> {
  if (!userId.value) return
  saving.value = true
  error.value = (await store.createEmployee(userId.value, blankToNull(work.value))) ?? ''
  saving.value = false
  if (error.value) return
  close()
  await router.push({ name: 'employee-profile', params: { userId: userId.value } })
}
</script>

<style scoped>
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
</style>
