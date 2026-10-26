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

<!-- Add or edit a leave type, on one policy or in the library. A policy's
     types are switched off, never deleted, so past requests keep their meaning. The
     caller saves (`save` returns an error message or null); the `actions`
     slot adds buttons at the start of the footer. -->
<template>
  <v-dialog :model-value="modelValue" max-width="600" :fullscreen="xs" scrollable @update:model-value="emit('update:modelValue', $event)">
    <v-card color="surface" rounded="lg">
      <div class="d-flex align-start ga-2 pa-6 pb-2">
        <div class="flex-grow-1">
          <h2 class="text-h6 font-weight-bold">{{ initial ? `Edit ${noun}` : `Add ${noun}` }}</h2>
          <p class="text-body-2 text-medium-emphasis">Applies to {{ draft.eligible_genders ? `people recorded as ${gendersLabel(draft.eligible_genders)}` : 'everyone' }} {{ scope }}.</p>
        </div>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="close" />
      </div>
      <v-card-text class="px-6">
        <AppCallout v-if="note" variant="info" class="mb-4">{{ note }}</AppCallout>
        <v-form class="d-flex flex-column" @submit.prevent="submit">
          <div class="group" role="group" :aria-labelledby="ids.basics">
            <div :id="ids.basics" class="group__title text-overline text-medium-emphasis">Basics</div>
            <LeaveTypeNameFields v-model:name="draft.name" v-model:code="draft.code" v-model:code-touched="codeTouched" />
          </div>
          <div class="group" role="group" :aria-labelledby="ids.allowance">
            <div :id="ids.allowance" class="group__title text-overline text-medium-emphasis">Allowance</div>
            <LeaveTypeAllowanceField v-model:unlimited="unlimited" v-model:days="quota" v-model:accrual="draft.accrual" v-model:stops="draft.stops_at_balance" />
            <LeaveTypeCarryField v-if="!unlimited" v-model="draft.carry_forward_days" class="mt-3" />
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
              v-if="initial && !library"
              v-model="draft.is_active"
              label="Available to request"
              description="Switch off to retire it. Past requests and balances are kept."
            />
          </div>
          <AppCallout v-if="error" variant="error" class="mt-2">{{ error }}</AppCallout>
        </v-form>
      </v-card-text>
      <v-divider />
      <div class="d-flex flex-wrap align-center ga-2 pa-4">
        <slot name="actions" />
        <v-spacer />
        <v-btn variant="text" @click="close">Cancel</v-btn>
        <v-btn color="primary" variant="flat" :loading="saving" :disabled="!valid" @click="submit">
          {{ initial ? 'Save changes' : `Add ${noun}` }}
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
import LeaveTypeCarryField from '@/components/leave/settings/LeaveTypeCarryField.vue'
import LeaveTypeColorPicker from '@/components/leave/settings/LeaveTypeColorPicker.vue'
import LeaveTypeNameFields from '@/components/leave/settings/LeaveTypeNameFields.vue'
import { usePermissions } from '@/composables/usePermissions'
import type { LeaveTypeWrite } from '@/types/leavePolicy'
import { toNumberOrNull } from '@/utils/leave'
import { gendersLabel } from '@/utils/leavePolicyDisplay'
import { blankType, validCarryForward, validMonthlyLimit } from '@/utils/leaveTypeDraft'

const props = defineProps<{
  modelValue: boolean
  /** The type being edited; null adds one. */
  initial: LeaveTypeWrite | null
  /** After "Applies to everyone": "on India", "on every policy that uses it". */
  scope: string
  save: (body: LeaveTypeWrite) => Promise<string | null>
  /** A new type's starting values (e.g. period leave). */
  preset?: LeaveTypeWrite | null
  /** A library type: no on/off switch, that's per policy. */
  library?: boolean
  /** Shown above the form, e.g. that an edit reaches every policy using it. */
  note?: string
}>()
const emit = defineEmits<(e: 'update:modelValue', value: boolean) => void>()

const DEFAULT_QUOTA = 12
const ids = { basics: useId(), allowance: useId(), access: useId(), appearance: useId() }
const noun = computed(() => (props.library ? 'library type' : 'leave type'))
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
    (unlimited.value || validCarryForward(draft.value.carry_forward_days)) &&
    (draft.value.eligible_genders === null || draft.value.eligible_genders.length > 0) &&
    !autoProblem.value,
)

watch(
  () => props.modelValue,
  open => {
    if (!open) return
    const start = props.initial ?? props.preset ?? blankType()
    draft.value = { ...start }
    const current = props.initial || props.preset ? toNumberOrNull(start.annual_quota_days) : DEFAULT_QUOTA
    unlimited.value = !!props.initial && current === null
    quota.value = current ?? DEFAULT_QUOTA
    codeTouched.value = !!props.initial || !!props.preset
    error.value = ''
  },
)

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
    carry_forward_days: unlimited.value ? null : draft.value.carry_forward_days,
  }
  error.value = (await props.save(body)) ?? ''
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
</style>
