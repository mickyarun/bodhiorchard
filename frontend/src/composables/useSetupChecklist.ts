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

import { computed, onMounted, onUnmounted, ref } from 'vue'
import api from '@/services/api'
import { useScanSocket, type RepoScanWarning, type ScanStatusData } from '@/composables/useScanSocket'
import { useScanStore } from '@/stores/scan'
import type { SetupChecklistStatus } from '@/types/setup'
import { setupChecklistItems, setupPollingDone, type SetupStep } from '@/utils/setupChecklist'

// Storage key predates the rename; installs already carry it.
const DISMISS_KEY = 'bodhiorchard_checklist_dismissed'
const POLL_MS = 10_000

/**
 * Setup progress for the dashboard: polls the checklist status, follows a
 * running scan over the socket for live progress, and lets the user hide
 * the card. A reset org (no org or no finished scan) brings it back.
 */
export function useSetupChecklist() {
  const scanStore = useScanStore()
  const { startTracking, stopTracking } = useScanSocket()

  const status = ref<SetupChecklistStatus | null>(null)
  const dismissed = ref(localStorage.getItem(DISMISS_KEY) === 'true')
  const scanLive = ref(false)
  const liveProgress = ref(0)
  const liveLabel = ref('')
  const warnings = ref<RepoScanWarning[]>([])
  const resuming = ref(false)
  let trackedScanId: string | null = null
  let poll: ReturnType<typeof setInterval> | null = null

  const scanning = computed(() => !!status.value?.scanInProgress || scanLive.value)
  const scanProgress = computed(() =>
    scanLive.value ? liveProgress.value : (status.value?.scanProgress ?? 0),
  )
  const scanLabel = computed(() => (scanLive.value && liveLabel.value) || 'Scanning repository…')
  const scanFailed = computed(() => scanStore.aggregateStatus === 'failed' && !scanLive.value)

  const steps = computed<SetupStep[]>(() =>
    status.value ? setupChecklistItems(status.value, scanning.value) : [],
  )
  const doneCount = computed(() => steps.value.filter(s => s.done).length)
  const nextStep = computed(() => steps.value.find(s => !s.done) ?? null)
  const visible = computed(() => !dismissed.value && !!status.value && !!nextStep.value)

  function track(scanId: string): void {
    if (trackedScanId === scanId) return
    if (trackedScanId) stopTracking()
    trackedScanId = scanId
    scanLive.value = true
    const finish = (): void => {
      scanLive.value = false
      trackedScanId = null
      void refresh()
    }
    startTracking(scanId, {
      onProgress: (data: ScanStatusData) => {
        liveProgress.value = data.progressPct || 0
        liveLabel.value = data.statusLabel || ''
        warnings.value = data.repoWarnings || []
        scanStore.ingestStatus(data)
      },
      onComplete: finish,
      onError: finish,
    })
  }

  function startPolling(): void {
    if (!poll) poll = setInterval(refresh, POLL_MS)
  }

  function stopPolling(): void {
    if (poll) clearInterval(poll)
    poll = null
  }

  async function refresh(): Promise<void> {
    try {
      const { data } = await api.get<SetupChecklistStatus>('/setup/checklist-status')
      status.value = data
      if (dismissed.value && (!data.orgCreated || !data.scanComplete)) {
        dismissed.value = false
        localStorage.removeItem(DISMISS_KEY)
        startPolling()
      }
      if (data.scanInProgress && data.scanId) track(data.scanId)
      if (setupPollingDone(data)) stopPolling()
    } catch {
      // The card is a convenience; a failed poll just leaves the last state.
    }
  }

  async function resumeScan(): Promise<void> {
    resuming.value = true
    try {
      const scanId = await scanStore.resume()
      if (scanId) track(scanId)
    } finally {
      resuming.value = false
    }
  }

  function dismiss(): void {
    dismissed.value = true
    localStorage.setItem(DISMISS_KEY, 'true')
    stopPolling()
    stopTracking()
    scanLive.value = false
    trackedScanId = null
  }

  onMounted(() => {
    // Fetch even when hidden, so a reset org brings the card back.
    void refresh()
    if (!dismissed.value) startPolling()
  })

  onUnmounted(() => {
    stopPolling()
    stopTracking()
  })

  return {
    visible,
    steps,
    doneCount,
    nextStep,
    scanning,
    scanProgress,
    scanLabel,
    scanFailed,
    phases: computed(() => scanStore.phases),
    warnings,
    resuming,
    resumeScan,
    dismiss,
  }
}
