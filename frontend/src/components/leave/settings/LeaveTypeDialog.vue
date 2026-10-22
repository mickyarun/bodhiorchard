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
          <p class="text-body-2 text-medium-emphasis">Applies to {{ draft.eligible_genders ? `people recorded as ${gendersLabel(draft.eligible_genders)}` : 'everyone' }} on {{ policyName }}.</p>
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
            <LeaveTypeAllowanceField v-model:unlimited="unlimited" v-model:days="quota" v-model:accrual="draft.accrual" v-model:stops="draft.stops_at_balance" />
          </div>
          <div class="group" role="group" :aria-labelledby="ids.access">
            <div :id="ids.access" class="group__title text-overline text-medium-emphasis">Who &amp; approval</div>
            <LeaveTypeAccessFields v-model:genders="draft.eligible_genders" v-model:auto-approve="draft.auto_approve" v-model:monthly-limit="draft.monthly_limit_days" />
            <p v-if="autoProblem" class="text-caption text-error mt-1">{{ autoProblem }}</p>
          </div>
          <div class="group" role="group" :aria-labelledby="ids.appearance">
            <div :id="ids.appearance" class="group__title text-overline text-medium-emphasis">Appearance &amp; status</div>
            <LeaveTypeColorPicker v-model="draft.color_key" :name="draft.name" class="mb-3" />
            <LeaveSwitchRow v-model="draft.is_paid" label="Paid leave" />
            <LeaveSwitchRow v-model="draft.is_encashable" label="Encashable at exit" description="Unused days are paid out when someone leaves." />
            <LeaveSwitchRow v-model="draft.counts_toward_warning" label="Counts toward the high-leave warning" description="Off for sick leave, usually. The lines are set in Rules." />
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
import LeaveTypeAccessFields from '@/components/leave/settings/LeaveTypeAccessFields.vue'
import LeaveTypeAllowanceField from '@/components/leave/settings/LeaveTypeAllowanceField.vue'
import LeaveTypeColorPicker from '@/components/leave/settings/LeaveTypeColorPicker.vue'
import { usePermissions } from '@/composables/usePermissions'
import { useLeavePolicyConfigStore } from '@/stores/leavePolicyConfig'
import type { LeaveTypeRead, LeaveTypeWrite } from '@/types/leavePolicy'
import { codeFromName, toNumberOrNull } from '@/utils/leave'
import { FIELD_PROPS, gendersLabel } from '@/utils/leavePolicyDisplay'
import { blankType, draftFromType, validMonthlyLimit } from '@/utils/leaveTypeDraft'

const props = defineProps<{
  modelValue: boolean
  policyId: string
  policyName: string
  type: LeaveTypeRead | null
  /** A new type's starting values (e.g. period leave); blank when absent. */
  preset?: LeaveTypeWrite | null
}>()
const emit = defineEmits<(e: 'update:modelValue', value: boolean) => void>()

const DEFAULT_QUOTA = 12
const ids = { basics: useId(), allowance: useId(), access: useId(), appearance: useId() }
const store = useLeavePolicyConfigStore()
const { canApproveLeave } = usePermissions()
const { xs } = useDisplay()
const draft = ref<LeaveTypeWrite>(blankType())
const quota = ref<number | null>(DEFAULT_QUOTA)
const unlimited = ref(false)
const codeTouched = ref(false)
const saving = ref(false)
const error = ref('')

const autoProblem = computed(() => {
  if (!draft.value.auto_approve) return ''
  if (!canApproveLeave.value) return 'Only people who approve leave can change a type that approves itself.'
  return unlimited.value ? 'A type that approves itself needs a yearly allowance, so extra days still go to a manager.' : ''
})

const valid = computed(
  () =>
    !!draft.value.name.trim() &&
    !!draft.value.code.trim() &&
    (unlimited.value || (typeof quota.value === 'number' && quota.value >= 0 && quota.value <= 365)) &&
    validMonthlyLimit(draft.value.monthly_limit_days) &&
    (draft.value.eligible_genders === null || draft.value.eligible_genders.length > 0) &&
    !autoProblem.value,
)

watch(
  () => props.modelValue,
  open => {
    if (!open) return
    const start = props.type ? draftFromType(props.type) : (props.preset ?? blankType())
    draft.value = { ...start }
    const current = props.type || props.preset ? toNumberOrNull(start.annual_quota_days) : DEFAULT_QUOTA
    unlimited.value = !!props.type && current === null
    quota.value = current ?? DEFAULT_QUOTA
    codeTouched.value = !!props.type || !!props.preset
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
    stops_at_balance: !unlimited.value && draft.value.stops_at_balance,
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
