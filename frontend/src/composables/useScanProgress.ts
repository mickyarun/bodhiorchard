// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Composable that surfaces the human-readable state of the active scan
 * (status chip tone/label, aggregate progress line). Pulled out of
 * RepoListHeader so any future surface — toolbar, toast, dashboard
 * widget — can reuse the same wording without duplicating the rules.
 */

import { computed, type ComputedRef } from 'vue'
import { useReposcanV2ScansStore } from '@/stores/reposcanv2Scans'

export interface ScanProgress {
  statusTone: ComputedRef<string>
  statusLabel: ComputedRef<string>
  progressSummary: ComputedRef<string>
}

export function useScanProgress(): ScanProgress {
  const store = useReposcanV2ScansStore()

  const statusTone = computed(() => {
    if (store.isCurrentScanActive) return 'primary'
    const status = store.currentScan?.status ?? ''
    if (status === 'failed') return 'error'
    if (status === 'completed') return 'success'
    return 'grey'
  })

  const statusLabel = computed(() => {
    if (store.isCurrentScanActive) return 'Running'
    return store.currentScan?.status?.toUpperCase() ?? '—'
  })

  const progressSummary = computed(() => {
    const c = store.aggregateCounts
    const parts: string[] = [`${c.done} of ${c.total} repos done`]
    if (c.running) parts.push(`${c.running} running`)
    if (c.failed) parts.push(`${c.failed} failed`)
    if (c.queued) parts.push(`${c.queued} queued`)
    if (c.features) parts.push(`${c.features} features`)
    return parts.join(' · ')
  })

  return { statusTone, statusLabel, progressSummary }
}
