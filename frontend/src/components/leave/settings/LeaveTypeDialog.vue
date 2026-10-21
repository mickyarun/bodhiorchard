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

<!-- Add or edit a leave type. Types are switched off, never deleted, so
     past requests keep their meaning. -->
<template>
  <v-dialog :model-value="modelValue" max-width="600" :fullscreen="xs" scrollable @update:model-value="emit('update:modelValue', $event)">
    <v-card color="surface" rounded="lg">
      <div class="d-flex align-start ga-2 pa-6 pb-2">
        <div class="flex-grow-1">
          <h2 class="text-h6 font-weight-bold">{{ type ? 'Edit leave type' : 'Add leave type' }}</h2>
          <p class="text-body-2 text-medium-emphasis">Applies to everyone on {{ policyName }}.</p>
        </div>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="close" />
      </div>
      <v-card-text class="px-6">
        <v-form class="d-flex flex-column" @submit.prevent="submit">
          <div class="group" role="group" :aria-labelledby="ids.basics">
            <div :id="ids.basics" class="group__title text-overline text-medium-emphasis">Basics</div>
            <div class="name-row">
              <v-text-field v-model="draft.name" label="Name" maxlength="100" autofocus v-bind="FIELD_PROPS" @update:model-value="syncCode" />
              <v-text-field
                v-model="draft.code"
                label="Code"
                maxlength="10"
                v-bind="FIELD_PROPS"
                @update:model-value="codeTouched = true"
              />
            </div>
            <p class="text-caption text-medium-emphasis mt-2">
              The code is a short ID for reports, filled in from the name.
            </p>
          </div>
          <div class="group" role="group" :aria-labelledby="ids.allowance">
            <div :id="ids.allowance" class="group__title text-overline text-medium-emphasis">Allowance</div>
            <LeaveTypeAllowanceField v-model:unlimited="unlimited" v-model:days="quota" v-model:accrual="draft.accrual" />
          </div>
          <div class="group" role="group" :aria-labelledby="ids.appearance">
            <div :id="ids.appearance" class="group__title text-overline text-medium-emphasis">Appearance &amp; status</div>
            <LeaveTypeColorPicker v-model="draft.color_key" :name="draft.name" class="mb-3" />
            <LeaveSwitchRow v-model="draft.is_paid" label="Paid leave" />
            <LeaveSwitchRow
              v-model="draft.is_encashable"
              label="Encashable at exit"
              description="Unused days are paid out when someone leaves."
            />
            <LeaveSwitchRow
              v-if="type"
              v-model="draft.is_active"
              label="Available to request"
              description="Switch off to retire it. Past requests and balances are kept."
            />
          </div>
          <AppCallout v-if="error" variant="error" class="mt-2">{{ error }}</AppCallout>
        </v-form>
      </v-card-text>
      <v-divider />
      <div class="d-flex justify-end ga-2 pa-4">
        <v-btn variant="text" @click="close">Cancel</v-btn>
        <v-btn color="primary" variant="flat" :loading="saving" :disabled="!valid" @click="submit">
          {{ type ? 'Save changes' : 'Add leave type' }}
        </v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, useId, watch } from 'vue'
import { useDisplay } from 'vuetify'
import AppCallout from '@/components/common/AppCallout.vue'
import LeaveSwitchRow from '@/components/leave/settings/LeaveSwitchRow.vue'
import LeaveTypeAllowanceField from '@/components/leave/settings/LeaveTypeAllowanceField.vue'
import LeaveTypeColorPicker from '@/components/leave/settings/LeaveTypeColorPicker.vue'
import { useLeavePolicyConfigStore } from '@/stores/leavePolicyConfig'
import type { LeaveTypeRead, LeaveTypeWrite } from '@/types/leavePolicy'
import { codeFromName, SWATCH_KEYS, toNumberOrNull } from '@/utils/leave'
import { FIELD_PROPS } from '@/utils/leavePolicyDisplay'

const props = defineProps<{
  modelValue: boolean
  policyId: string
  policyName: string
  type: LeaveTypeRead | null
}>()
const emit = defineEmits<(e: 'update:modelValue', value: boolean) => void>()

const DEFAULT_QUOTA = 12
const ids = { basics: useId(), allowance: useId(), appearance: useId() }
const store = useLeavePolicyConfigStore()
const { xs } = useDisplay()
const draft = ref<LeaveTypeWrite>(blank())
const quota = ref<number | null>(DEFAULT_QUOTA)
const unlimited = ref(false)
const codeTouched = ref(false)
const saving = ref(false)
const error = ref('')

const valid = computed(
  () =>
    !!draft.value.name.trim() &&
    !!draft.value.code.trim() &&
    (unlimited.value || (typeof quota.value === 'number' && quota.value >= 0 && quota.value <= 365)),
)

function blank(): LeaveTypeWrite {
  return {
    name: '',
    code: '',
    annual_quota_days: null,
    accrual: 'upfront',
    is_paid: true,
    is_encashable: false,
    color_key: SWATCH_KEYS[0],
    is_active: true,
  }
}

function fromType(type: LeaveTypeRead): LeaveTypeWrite {
  const { name, code, annual_quota_days, accrual, is_paid, is_encashable, color_key, is_active } = type
  return { name, code, annual_quota_days, accrual, is_paid, is_encashable, color_key, is_active }
}

watch(
  () => props.modelValue,
  open => {
    if (!open) return
    const type = props.type
    draft.value = type ? fromType(type) : blank()
    const current = type ? toNumberOrNull(type.annual_quota_days) : DEFAULT_QUOTA
    unlimited.value = !!type && current === null
    quota.value = current ?? DEFAULT_QUOTA
    codeTouched.value = !!type
    error.value = ''
  },
)

function syncCode(name: string): void {
  if (!codeTouched.value) draft.value.code = codeFromName(name)
}

function close(): void {
  emit('update:modelValue', false)
}

async function submit(): Promise<void> {
  if (!valid.value) return
  saving.value = true
  const body: LeaveTypeWrite = {
    ...draft.value,
    name: draft.value.name.trim(),
    code: draft.value.code.trim().toUpperCase(),
    annual_quota_days: unlimited.value ? null : quota.value,
    // An unlimited type has nothing to release month by month.
    accrual: unlimited.value ? 'upfront' : draft.value.accrual,
  }
  error.value = (await store.saveType(props.policyId, body, props.type?.id ?? null)) ?? ''
  saving.value = false
  if (!error.value) close()
}
</script>

<style scoped>
.group {
  padding: 0 0 20px;
}
.group + .group {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  padding-top: 16px;
}
.group__title {
  margin-bottom: 8px;
  line-height: 1.6;
}
.name-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 160px;
  gap: 16px;
  align-items: start;
}
@media (max-width: 600px) {
  .name-row {
    grid-template-columns: 1fr;
  }
}
</style>
