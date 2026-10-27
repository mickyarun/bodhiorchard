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

<!-- Request leave, work from home or an optional holiday, with a live
     preview of the cost and the approver before sending. -->
<template>
  <v-dialog
    :model-value="modelValue"
    max-width="560"
    :fullscreen="xs"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card class="pa-0">
      <div class="d-flex align-center justify-space-between pa-6 pb-3">
        <h2 class="text-h6 font-weight-bold">New request</h2>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="close" />
      </div>
      <v-form class="px-6 d-flex flex-column ga-4" @submit.prevent="submit">
        <AppPillToggle v-if="kindOptions.length > 1" v-model="form.kind.value" :options="kindOptions" class="align-self-start" />
        <LeaveBalanceStrip v-if="summary" :summary="summary" :kind="form.kind.value" :selected-type-id="form.leaveTypeId.value" />
        <v-select
          v-if="form.kind.value === 'leave'"
          v-model="form.leaveTypeId.value"
          :items="typeItems"
          label="Leave type"
          no-data-text="HR hasn't added leave types yet."
          v-bind="field"
        />
        <v-select
          v-if="form.kind.value === 'optional_holiday'"
          v-model="form.holidayId.value"
          :items="holidayItems"
          label="Holiday"
          no-data-text="No optional holidays left this year."
          v-bind="field"
        />
        <div v-else class="date-row">
          <v-text-field v-model="form.startDate.value" label="From" type="date" v-bind="field" />
          <v-text-field
            v-model="form.endDate.value"
            label="To"
            type="date"
            :min="form.startDate.value"
            v-bind="field"
          />
        </div>
        <AppPillToggle
          v-if="form.singleDay.value && form.kind.value !== 'optional_holiday'"
          v-model="form.halfDay.value"
          :options="HALF_DAY_OPTIONS"
          size="sm"
          class="align-self-start"
        />
        <v-textarea
          v-model="form.reason.value"
          label="Reason (optional)"
          rows="2"
          auto-grow
          counter="500"
          maxlength="500"
          hint="Only your managers and HR can see this."
          persistent-hint
          v-bind="field"
        />
        <LeavePreviewPanel
          :preview="form.preview.value"
          :previewing="form.previewing.value"
          :error="form.previewError.value"
          :kind="form.kind.value"
          :policy="summary?.policy ?? null"
          :type-name="selectedTypeName"
          placeholder="Pick the dates to see how many days this uses."
        />
        <AppCallout v-if="error" variant="error">{{ error }}</AppCallout>
      </v-form>
      <div class="d-flex justify-end ga-2 pa-6 pt-4">
        <v-btn variant="text" @click="close">Cancel</v-btn>
        <v-btn color="primary" :loading="sending" :disabled="!form.canSend.value" @click="submit">
          Send request
        </v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import LeaveBalanceStrip from '@/components/leave/LeaveBalanceStrip.vue'
import LeavePreviewPanel from '@/components/leave/LeavePreviewPanel.vue'
import { useLeaveRequestForm } from '@/composables/useLeaveRequestForm'
import { useLeaveStore } from '@/stores/leave'
import type { HalfDay, LeaveKind } from '@/types/leave'
import { HALF_DAY_LABELS, KIND_LABELS, pillOptions, pluralDays, toNumber } from '@/utils/leave'
import { daysLeftForDraft } from '@/utils/leaveAccrual'
import { formatDayRange } from '@/utils/leaveDates'

const props = defineProps<{ modelValue: boolean; preset: LeaveKind }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; sent: [] }>()

const { xs } = useDisplay()
const store = useLeaveStore()
const form = useLeaveRequestForm()
const field = { variant: 'outlined', density: 'compact', hideDetails: 'auto' } as const
const HALF_DAY_OPTIONS: { label: string; value: HalfDay }[] = pillOptions(HALF_DAY_LABELS)
const sending = ref(false)
const error = ref('')

const summary = computed(() => store.summary)

const kindOptions = computed(() => {
  // Remote people work from home every day: there's nothing to request.
  const kinds: LeaveKind[] = summary.value?.work_arrangement === 'remote' ? ['leave'] : ['leave', 'wfh']
  if ((summary.value?.optional_holidays.quota ?? 0) > 0) kinds.push('optional_holiday')
  return kinds.map(value => ({ label: KIND_LABELS[value], value }))
})

const typeItems = computed(() =>
  (summary.value?.balances ?? []).map(b => {
    const left = daysLeftForDraft(b, form.preview.value)
    return {
      title: left === null
        ? `${b.leave_type.name} · No limit`
        : `${b.leave_type.name} · ${pluralDays(toNumber(left))} left`,
      value: b.leave_type.id,
    }
  }),
)

const holidayItems = computed(() =>
  (summary.value?.optional_holidays.holidays ?? []).map(h => ({
    title: `${h.name} · ${formatDayRange(h.date, h.date)}`,
    value: h.id,
  })),
)

const selectedTypeName = computed(
  () =>
    summary.value?.balances.find(b => b.leave_type.id === form.leaveTypeId.value)?.leave_type
      .name ?? '',
)

// An optional holiday's date is the holiday itself: also when switching
// back to this kind after editing the (hidden) dates for leave or WFH.
watch([form.kind, form.holidayId], ([kind, id]) => {
  if (kind !== 'optional_holiday') return
  const holiday = summary.value?.optional_holidays.holidays.find(h => h.id === id)
  if (!holiday) return
  form.startDate.value = holiday.date
  form.endDate.value = holiday.date
})

watch(
  () => props.modelValue,
  open => {
    if (!open) return
    form.reset(props.preset)
    error.value = ''
  },
)

function close(): void {
  emit('update:modelValue', false)
}

async function submit(): Promise<void> {
  const body = form.payload.value
  if (!body || !form.canSend.value) return
  sending.value = true
  error.value = (await store.createRequest(body)) ?? ''
  sending.value = false
  if (error.value) return
  emit('sent')
  close()
}
</script>

<style scoped>
.date-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
</style>
