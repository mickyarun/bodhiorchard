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
