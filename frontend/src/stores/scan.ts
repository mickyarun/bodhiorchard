// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Pinia store for scan state.
 *
 * Centralises the scan data that `SetupChecklist.vue` and the new
 * `ScanPhaseTimeline.vue` both read from, and exposes the two admin
 * actions the timeline surfaces: resume and per-phase retry. The
 * WebSocket tracker (`useScanSocket`) writes into this store on every
 * tick so components only read refs, never own their own copies.
 */

import axios from 'axios'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import type {
  PhaseStatus,
  ScanPhaseCode,
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

  /** POST `/scan/{id}/resume` and hand the returned child scan_id back
   * to the caller so it can swap its active tracker. Does not touch
   * store state directly — the tracker's next tick will do it. */
  async function resume(): Promise<string | null> {
    const parent = currentScanId.value
    if (!parent) return null
    const res = await axios.post<{ newScanId: string }>(
      `/v1/skills/scan/${parent}/resume`,
    )
    return res.data.newScanId
  }

  /** POST `/scan/{id}/phases/{phase}/retry`, optionally scoped to a
   * single repo. Returns the child scan_id the tracker should switch to. */
  async function retryPhase(
    phase: ScanPhaseCode,
    repoId?: string | null,
  ): Promise<string | null> {
    const parent = currentScanId.value
    if (!parent) return null
    const url = `/v1/skills/scan/${parent}/phases/${phase}/retry`
    const res = await axios.post<{ newScanId: string }>(
      url,
      null,
      repoId ? { params: { repo_id: repoId } } : undefined,
    )
    return res.data.newScanId
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
    retryPhase,
  }
})
