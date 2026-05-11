// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * Pinia store for scan state.
 *
 * Centralises the scan data that `SetupChecklist.vue` and
 * `ScanPhaseTimeline.vue` both read from, and exposes the resume
 * action the timeline surfaces. The WebSocket tracker (`useScanSocket`)
 * writes into this store on every tick so components only read refs,
 * never own their own copies.
 */

import axios from 'axios'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import type {
  PhaseStatus,
  ScanStatusData,
} from '@/composables/useScanSocket'

/** Aggregate lifecycle state — computed from `status` plus whether
 * the tracker currently thinks the scan is active. The UI gates the
 * "Resume scan" button on this (only visible when `failed`). */
export type ScanAggregateStatus = 'idle' | 'running' | 'completed' | 'failed'

export const useScanStore = defineStore('scan', () => {
  const currentScanId = ref<string | null>(null)
  const parentScanId = ref<string | null>(null)
  const phases = ref<PhaseStatus[]>([])
  const status = ref<string>('')
  const progressPct = ref<number>(0)
  const statusLabel = ref<string>('')
  const repoWarnings = ref<ScanStatusData['repoWarnings']>([])
  const synthesisWarning = ref<string | null>(null)
  const error = ref<string | null>(null)

  const aggregateStatus = computed<ScanAggregateStatus>(() => {
    if (!currentScanId.value) return 'idle'
    if (status.value === 'completed') return 'completed'
    if (status.value === 'failed') return 'failed'
    return 'running'
  })

  /** Called by `useScanSocket` on every WS / poll tick. */
  function ingestStatus(next: ScanStatusData): void {
    currentScanId.value = next.scanId
    parentScanId.value = next.parentScanId
    phases.value = next.phases ?? []
    status.value = next.status
    progressPct.value = next.progressPct
    statusLabel.value = next.statusLabel
    repoWarnings.value = next.repoWarnings ?? []
    synthesisWarning.value = next.synthesisWarning
    error.value = next.error
  }

  /** Called when the tracker stops (terminal status or unmount). */
  function reset(): void {
    currentScanId.value = null
    parentScanId.value = null
    phases.value = []
    status.value = ''
    progressPct.value = 0
    statusLabel.value = ''
    repoWarnings.value = []
    synthesisWarning.value = null
    error.value = null
  }

  /** Re-queue any non-DONE repo runs in the current scan. The new
   * pipeline reuses the same scan id (no child scan), so the tracker
   * keeps polling the same id and observes the resumed runs flip back
   * to RUNNING then DONE. */
  async function resume(): Promise<string | null> {
    const parent = currentScanId.value
    if (!parent) return null
    await axios.post(`/v1/reposcanv2/scans/${parent}/resume`)
    return parent
  }

  return {
    // state
    currentScanId,
    parentScanId,
    phases,
    status,
    progressPct,
    statusLabel,
    repoWarnings,
    synthesisWarning,
    error,
    aggregateStatus,
    // mutations
    ingestStatus,
    reset,
    // actions
    resume,
  }
})
