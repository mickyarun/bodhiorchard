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

<!-- Add or remove days from one member's balance (leave:configure).
     Every adjustment needs a note; it shows in the ledger. -->
<template>
  <v-dialog :model-value="modelValue" max-width="480" @update:model-value="emit('update:modelValue', $event)">
    <v-card class="pa-0">
      <div class="d-flex align-center justify-space-between pa-6 pb-2">
        <h2 class="text-h6 font-weight-bold">Adjust balance</h2>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="close" />
      </div>
      <v-form class="px-6 d-flex flex-column ga-3" @submit.prevent="submit">
        <v-select v-model="typeId" :items="typeItems" label="Leave type" v-bind="field" />
        <v-text-field
          v-model.number="days"
          label="Days (negative removes)"
          type="number"
          step="0.5"
          min="-365"
          max="365"
          prepend-inner-icon="mdi-minus"
          append-inner-icon="mdi-plus"
          v-bind="field"
          @click:prepend-inner="days = step(-STEP)"
          @click:append-inner="days = step(STEP)"
        />
        <v-textarea v-model="note" label="Note" rows="2" auto-grow counter="500" maxlength="500" v-bind="field" />
        <div v-if="previewLine" class="text-body-2">{{ previewLine }}</div>
        <AppCallout v-if="error" variant="error">{{ error }}</AppCallout>
      </v-form>
      <div class="d-flex justify-end ga-2 pa-6 pt-4">
        <v-btn variant="text" @click="close">Cancel</v-btn>
        <v-btn color="primary" :loading="saving" :disabled="!valid" @click="submit">Save adjustment</v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import type { Balance } from '@/types/leave'
import type { BalanceAdjust } from '@/types/leavePolicy'
import { formatDays, toNumberOrNull } from '@/utils/leave'

const STEP = 0.5
const MIN_NOTE = 3

const props = defineProps<{
  modelValue: boolean
  balances: Balance[]
  leaveYear: number
  save: (body: BalanceAdjust) => Promise<string | null>
}>()
const emit = defineEmits<(e: 'update:modelValue', value: boolean) => void>()

const field = { variant: 'outlined', density: 'compact', hideDetails: 'auto' } as const
const typeId = ref<string | null>(null)
const days = ref<number>(0)
const note = ref('')
const saving = ref(false)
const error = ref('')

const typeItems = computed(() =>
  props.balances.map(b => ({ title: b.leave_type.name, value: b.leave_type.id })),
)
const selected = computed(() => props.balances.find(b => b.leave_type.id === typeId.value) ?? null)
const valid = computed(
  () =>
    !!typeId.value &&
    typeof days.value === 'number' &&
    days.value !== 0 &&
    Math.abs(days.value) <= 365 &&
    note.value.trim().length >= MIN_NOTE,
)

const previewLine = computed(() => {
  const balance = selected.value
  if (!balance || typeof days.value !== 'number' || !days.value) return ''
  const before = toNumberOrNull(balance.available)
  if (before === null) return `${balance.leave_type.name} has no limit; this is recorded in the ledger.`
  const after = before + days.value
  return `${balance.leave_type.name}: ${formatDays(before)} → ${formatDays(after)} ${after === 1 ? 'day' : 'days'} left`
})

function step(delta: number): number {
  const current = typeof days.value === 'number' ? days.value : 0
  return Math.max(-365, Math.min(365, current + delta))
}

watch(
  () => props.modelValue,
  open => {
    if (!open) return
    typeId.value = props.balances[0]?.leave_type.id ?? null
    days.value = 0
    note.value = ''
    error.value = ''
  },
)

function close(): void {
  emit('update:modelValue', false)
}

async function submit(): Promise<void> {
  if (!valid.value || !typeId.value) return
  saving.value = true
  error.value =
    (await props.save({
      leave_type_id: typeId.value,
      days: Math.round(days.value * 10) / 10,
      note: note.value.trim(),
      leave_year: props.leaveYear,
    })) ?? ''
  saving.value = false
  if (!error.value) close()
}
</script>
