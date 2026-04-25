<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Arun Rajkumar -->
<template>
  <div v-if="phases.length" class="scan-phase-timeline">
    <v-timeline density="compact" side="end" truncate-line="both">
      <v-timeline-item
        v-for="row in phases"
        :key="`${row.phase}:${row.repoId ?? 'global'}:${row.attempt}`"
        :dot-color="phaseColor(row)"
        :icon="phaseIcon(row)"
        size="x-small"
      >
        <div :class="['phase-row', { 'phase-row--failed': row.status === 'failed' }]">
          <div class="phase-head">
            <span :class="['phase-label', { 'phase-label--failed': row.status === 'failed' }]">
              {{ row.phaseLabel }}
            </span>
            <span v-if="row.repoName" class="phase-repo">{{ row.repoName }}</span>
            <v-chip
              v-if="row.attempt > 1"
              size="x-small"
              color="warning"
              variant="tonal"
              label
            >attempt {{ row.attempt }}</v-chip>
            <v-chip
              v-if="row.shaReused"
              size="x-small"
              color="info"
              variant="tonal"
              label
              prepend-icon="mdi-cached"
            >cached</v-chip>
            <v-chip
              v-if="row.status === 'failed'"
              size="x-small"
              color="error"
              variant="flat"
              label
            >Failed</v-chip>
          </div>
          <div v-if="row.errorMessage" class="phase-error">
            <span v-if="row.errorCode" class="phase-error-code">{{ row.errorCode }}</span>
            <span>{{ row.errorMessage }}</span>
          </div>
          <div v-if="row.status === 'failed'" class="phase-actions">
            <v-btn
              variant="flat"
              color="primary"
              size="small"
              prepend-icon="mdi-refresh"
              :loading="resuming || retrying === retryKey(row)"
              @click="onRetry(row)"
            >Resume from here</v-btn>
          </div>
        </div>
      </v-timeline-item>
    </v-timeline>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

import type { PhaseStatus } from '@/composables/useScanSocket'

interface Props {
  phases: PhaseStatus[]
  resuming?: boolean
}
interface Emits {
  (event: 'retry', row: PhaseStatus): void
}

withDefaults(defineProps<Props>(), { resuming: false })
const emit = defineEmits<Emits>()

// Tracks which row is currently mid-retry so its button shows a
// spinner. Keyed by (phase, repoId, attempt) — same shape as the
// v-for key so each row's state is independent.
const retrying = ref<string | null>(null)

function retryKey(row: PhaseStatus): string {
  return `${row.phase}:${row.repoId ?? 'global'}:${row.attempt}`
}

async function onRetry(row: PhaseStatus): Promise<void> {
  retrying.value = retryKey(row)
  try {
    emit('retry', row)
  } finally {
    // The parent swaps the active scanId on successful retry, which
    // unmounts this component. On failure, we just reset the spinner.
    retrying.value = null
  }
}

function phaseColor(row: PhaseStatus): string {
  if (row.shaReused) return 'info'
  switch (row.status) {
    case 'done':
      return 'success'
    case 'failed':
      return 'error'
    case 'running':
      return 'primary'
    case 'skipped':
      return 'grey'
    case 'pending':
    default:
      return 'grey-lighten-1'
  }
}

function phaseIcon(row: PhaseStatus): string {
  if (row.shaReused) return 'mdi-cached'
  switch (row.status) {
    case 'done':
      return 'mdi-check-circle'
    case 'failed':
      return 'mdi-alert-circle'
    case 'running':
      return 'mdi-loading mdi-spin'
    case 'skipped':
      return 'mdi-minus-circle-outline'
    case 'pending':
    default:
      return 'mdi-circle-outline'
  }
}
</script>

<style scoped>
.scan-phase-timeline {
  padding: 8px 0;
}
.phase-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 4px 8px 6px;
  border-radius: 6px;
  transition: background-color 120ms ease;
}
.phase-row--failed {
  background: rgba(var(--v-theme-error), 0.08);
  border-left: 2px solid rgb(var(--v-theme-error));
  padding-left: 10px;
}
.phase-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.phase-label {
  font-weight: 500;
  color: rgb(var(--v-theme-on-surface));
}
.phase-label--failed {
  color: rgb(var(--v-theme-error));
}
.phase-repo {
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.85rem;
}
.phase-error {
  font-size: 0.8rem;
  color: rgb(var(--v-theme-on-surface-variant));
  display: flex;
  gap: 6px;
  align-items: baseline;
}
.phase-error-code {
  font-family: var(--font-mono, monospace);
  font-weight: 600;
  color: rgb(var(--v-theme-error));
}
.phase-actions {
  padding-top: 4px;
}
</style>
