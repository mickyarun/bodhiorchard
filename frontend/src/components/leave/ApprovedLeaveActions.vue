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

<!-- Approvals → Decided: approved leave that isn't over can still be moved or
     have its approval withdrawn by their managers, HR or the owner. Leave
     already under way keeps its start: only the end moves, or the rest is
     withdrawn. The requester is told either way. -->
<template>
  <div>
    <template v-if="mode === 'move'">
      <div class="date-grid">
        <v-text-field v-model="start" label="From" type="date" :disabled="started" v-bind="field" />
        <v-text-field v-model="end" label="To" type="date" :min="started ? today : start" v-bind="field" />
        <v-select
          v-if="!started && start === end"
          v-model="halfDay"
          :items="halfDayItems"
          label="Day"
          v-bind="field"
        />
      </div>
      <p v-if="started" class="text-caption text-medium-emphasis mt-2">
        This leave has started, so only its end date can change.
      </p>
    </template>
    <v-textarea
      v-if="mode"
      v-model="note"
      :label="mode === 'withdraw' ? 'Why are you withdrawing the approval?' : 'Note for them (optional)'"
      hint="They'll see this note."
      persistent-hint
      rows="2"
      auto-grow
      counter="500"
      maxlength="500"
      class="mt-3"
      v-bind="field"
    />
    <AppCallout v-if="error" variant="error" class="mt-3">{{ error }}</AppCallout>
    <div class="d-flex justify-end flex-wrap ga-2" :class="{ 'mt-3': mode }">
      <template v-if="mode">
        <v-btn variant="text" @click="close">Back</v-btn>
        <v-btn v-if="mode === 'move'" color="primary" variant="flat" :loading="busy" @click="submitMove">
          Save new dates
        </v-btn>
        <v-btn
          v-else
          color="error"
          variant="outlined"
          :loading="busy"
          :disabled="!note.trim()"
          @click="submitWithdraw"
        >
          {{ started ? 'End it today' : 'Withdraw approval' }}
        </v-btn>
      </template>
      <template v-else>
        <v-btn v-if="request.kind !== 'optional_holiday'" variant="text" size="small" @click="open('move')">
          Change dates
        </v-btn>
        <v-btn variant="text" size="small" color="error" @click="open('withdraw')">
          {{ started ? 'End early' : 'Withdraw approval' }}
        </v-btn>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import { useLeaveApprovalsStore } from '@/stores/leaveApprovals'
import type { HalfDay, LeaveRequestRead } from '@/types/leave'
import { HALF_DAY_LABELS } from '@/utils/leave'

const props = defineProps<{ request: LeaveRequestRead }>()
const store = useLeaveApprovalsStore()
const field = { variant: 'outlined', density: 'compact', hideDetails: 'auto' } as const

const today = new Date().toLocaleDateString('en-CA') // YYYY-MM-DD, local
const started = computed(() => props.request.start_date < today)
const halfDayItems = (Object.keys(HALF_DAY_LABELS) as HalfDay[]).map(value => ({
  title: HALF_DAY_LABELS[value],
  value,
}))

const mode = ref<'move' | 'withdraw' | null>(null)
const start = ref('')
const end = ref('')
const halfDay = ref<HalfDay>('none')
const note = ref('')
const busy = ref(false)
const error = ref('')

function open(next: 'move' | 'withdraw'): void {
  start.value = props.request.start_date
  end.value = props.request.end_date
  halfDay.value = props.request.half_day
  note.value = ''
  error.value = ''
  mode.value = next
}

function close(): void {
  mode.value = null
  error.value = ''
}

async function run(call: () => Promise<string | null>): Promise<void> {
  busy.value = true
  error.value = (await call()) ?? ''
  busy.value = false
  if (!error.value) mode.value = null
}

function submitMove(): Promise<void> {
  const single = start.value === end.value
  return run(() =>
    store.reschedule(props.request.id, {
      start_date: start.value,
      end_date: end.value,
      half_day: single ? halfDay.value : 'none',
      note: note.value,
    }),
  )
}

function submitWithdraw(): Promise<void> {
  return run(() => store.withdraw(props.request.id, note.value))
}
</script>

<style scoped>
.date-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}
@media (max-width: 600px) {
  .date-grid {
    grid-template-columns: 1fr;
  }
}
</style>
