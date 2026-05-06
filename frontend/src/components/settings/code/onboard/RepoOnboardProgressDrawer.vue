<!--
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2026 Arun Rajkumar

  Live progress for an in-flight bulk-onboard job. Subscribes via
  ``useJobSocket`` and renders one row per item plus an overall
  progress bar. On terminal completion emits ``@complete`` with the
  parsed terminal result so the orchestrator can flip into the ``done``
  state and present a summary.
-->
<template>
  <v-card variant="outlined" class="pa-4">
    <div class="d-flex align-center ga-2 mb-2">
      <v-progress-circular v-if="isActive" indeterminate size="18" width="2" />
      <span class="text-body-2 font-weight-medium">{{ headerMessage }}</span>
      <v-spacer />
      <v-btn v-if="!isActive" size="small" variant="text" @click="emit('cancel')">
        {{ DISMISS_LABEL }}
      </v-btn>
    </div>
    <v-progress-linear :model-value="overallPct" height="6" rounded class="mb-3" />
    <v-list density="compact" lines="one" class="py-0">
      <v-list-item v-for="item in items" :key="item.fullName">
        <v-list-item-title class="text-body-2">{{ item.fullName }}</v-list-item-title>
        <template #append>
          <v-chip size="x-small" :color="chipColorFor(item.status)" variant="tonal">
            {{ item.status }}
          </v-chip>
        </template>
      </v-list-item>
    </v-list>
    <v-alert v-if="errorMessage" type="error" variant="tonal" class="mt-3" density="compact">
      {{ errorMessage }}
    </v-alert>
  </v-card>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useJobSocket } from '@/composables/useJobSocket'
import {
  BULK_ONBOARD_ITEM_STATE,
  type BulkOnboardItemProgress,
  type BulkOnboardItemState,
  type BulkOnboardJobProgressResult,
  type BulkOnboardJobTerminalResult,
} from '@/types/repoOnboard'

const DISMISS_LABEL = 'Dismiss'
const RUNNING_MESSAGE = 'Cloning repositories…'
const COMPLETE_MESSAGE = 'Onboarding complete.'
const FAILED_MESSAGE = 'Onboarding failed.'

const props = defineProps<{ jobId: string }>()
const emit = defineEmits<{
  complete: [BulkOnboardJobTerminalResult]
  cancel: []
}>()

const tracker = useJobSocket()
const errorMessage = ref<string | null>(null)
const terminal = ref<BulkOnboardJobTerminalResult | null>(null)

const items = computed<BulkOnboardItemProgress[]>(() => {
  const result = (terminal.value ?? extractProgress(tracker.status.value?.result)) as
    | BulkOnboardJobProgressResult
    | BulkOnboardJobTerminalResult
    | null
  return result?.items ?? []
})

const isActive = computed(() => tracker.isActive.value && terminal.value === null)

const overallPct = computed(() => {
  const all = items.value
  if (all.length === 0) return tracker.status.value?.progressPct ?? 0
  const done = all.filter(
    (i) =>
      i.status === BULK_ONBOARD_ITEM_STATE.DONE || i.status === BULK_ONBOARD_ITEM_STATE.ERROR,
  ).length
  return Math.round((done / all.length) * 100)
})

const headerMessage = computed(() => {
  if (errorMessage.value) return FAILED_MESSAGE
  if (terminal.value) return COMPLETE_MESSAGE
  return RUNNING_MESSAGE
})

function extractProgress(
  result: unknown,
): BulkOnboardJobProgressResult | BulkOnboardJobTerminalResult | null {
  if (!result || typeof result !== 'object') return null
  return result as BulkOnboardJobProgressResult | BulkOnboardJobTerminalResult
}

function chipColorFor(status: BulkOnboardItemState): string {
  switch (status) {
    case BULK_ONBOARD_ITEM_STATE.DONE:
      return 'success'
    case BULK_ONBOARD_ITEM_STATE.ERROR:
      return 'error'
    case BULK_ONBOARD_ITEM_STATE.CLONING:
      return 'info'
    default:
      return 'default'
  }
}

onMounted(() => {
  tracker.startTracking(props.jobId, {
    onComplete: (result) => {
      const parsed = extractProgress(result) as BulkOnboardJobTerminalResult | null
      if (parsed) {
        terminal.value = parsed
        emit('complete', parsed)
      }
    },
    onError: (err) => {
      errorMessage.value = err
    },
  })
})

onBeforeUnmount(() => {
  tracker.stopTracking()
})
</script>
