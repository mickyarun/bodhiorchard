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

<!-- Request leave, work from home or an optional holiday, in a panel from
     the right (full screen on phones), with a live preview of the cost and
     the approver before sending. -->
<template>
  <AppSideSheet
    :model-value="modelValue"
    :title="TITLES[form.kind.value]"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-form class="request-form" @submit.prevent="submit">
      <AppPillToggle
        v-if="kindOptions.length > 1"
        v-model="form.kind.value"
        :options="kindOptions"
        aria-label="Request type"
        class="align-self-start"
      />
      <LeaveBalanceStrip v-if="summary" :summary="summary" :kind="form.kind.value" :selected-type-id="form.leaveTypeId.value" />
      <LeaveTypePicker v-if="form.kind.value === 'leave'" v-model="form.leaveTypeId.value" :balances="summary?.balances ?? []" :preview="form.preview.value" />
      <v-select
        v-if="form.kind.value === 'optional_holiday'"
        v-model="form.holidayId.value"
        :items="holidayItems"
        label="Holiday"
        no-data-text="No optional holidays left this year."
        v-bind="field"
      />
      <div v-else class="request-form__dates">
        <v-text-field v-model="form.startDate.value" label="From" type="date" v-bind="field" />
        <v-text-field v-model="form.endDate.value" label="To" type="date" :min="form.startDate.value" v-bind="field" />
      </div>
      <AppPillToggle
        v-if="form.singleDay.value && form.kind.value !== 'optional_holiday'"
        v-model="form.halfDay.value"
        :options="HALF_DAY_OPTIONS"
        size="sm"
        aria-label="Part of the day"
        class="align-self-start"
      />
      <v-textarea
        v-model="form.reason.value"
        label="Reason (optional)"
        rows="3"
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
    <template #actions>
      <v-btn variant="outlined" @click="close">Cancel</v-btn>
      <v-btn color="primary" variant="flat" :loading="sending" :disabled="!form.canSend.value" @click="submit">
        Send request
      </v-btn>
    </template>
  </AppSideSheet>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import AppSideSheet from '@/components/common/AppSideSheet.vue'
import LeaveBalanceStrip from '@/components/leave/LeaveBalanceStrip.vue'
import LeavePreviewPanel from '@/components/leave/LeavePreviewPanel.vue'
import LeaveTypePicker from '@/components/leave/LeaveTypePicker.vue'
import { useLeaveRequestForm } from '@/composables/useLeaveRequestForm'
import { useLeaveStore } from '@/stores/leave'
import type { HalfDay, LeaveKind } from '@/types/leave'
import { HALF_DAY_LABELS, KIND_LABELS, KIND_SHORT_LABELS, pillOptions } from '@/utils/leave'
import { formatDayRange } from '@/utils/leaveDates'

const props = defineProps<{ modelValue: boolean; preset: LeaveKind }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean]; sent: [] }>()

const { xs } = useDisplay()
const store = useLeaveStore()
const form = useLeaveRequestForm()
const field = { variant: 'outlined', density: 'compact', hideDetails: 'auto' } as const
const TITLES: Record<LeaveKind, string> = {
  leave: 'Request leave',
  wfh: 'Work from home',
  optional_holiday: 'Take an optional holiday',
}
const HALF_DAY_OPTIONS: { label: string; value: HalfDay }[] = pillOptions(HALF_DAY_LABELS)
const sending = ref(false)
const error = ref('')

const summary = computed(() => store.summary)

const kindOptions = computed(() => {
  // Remote people work from home every day: there's nothing to request.
  const kinds: LeaveKind[] = summary.value?.work_arrangement === 'remote' ? ['leave'] : ['leave', 'wfh']
  if ((summary.value?.optional_holidays.quota ?? 0) > 0) kinds.push('optional_holiday')
  // "Work from home" wraps inside the toggle on a phone.
  const labels = xs.value ? KIND_SHORT_LABELS : KIND_LABELS
  return kinds.map(value => ({ label: labels[value], value }))
})

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
.request-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.request-form__dates {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
</style>
