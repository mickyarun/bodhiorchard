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
 * Pure helpers used by RepoListRow.vue. Pulled out so the SFC can stay
 * under the project's 200-line ceiling once the setup-status chip lands.
 *
 * No Vue imports here — the helpers are runtime-pure and trivially
 * unit-testable (and could move into a util-test file without dragging
 * the component along for the ride).
 */

import type { LastScanStatus } from '@/types'

export interface LastScanSummary {
  label: string
  color: string
  icon: string
  relativeTime: string
  featureCount: number | null
}

export const STATUS_PRESENTATION: Record<
  LastScanStatus,
  { label: string, color: string, icon: string }
> = {
  done: { label: 'Synthesis done', color: 'success', icon: 'mdi-check-circle-outline' },
  skipped_unchanged: { label: 'Unchanged', color: 'info', icon: 'mdi-equal-box' },
  failed: { label: 'Failed', color: 'error', icon: 'mdi-alert-circle-outline' },
  cancelled: { label: 'Cancelled', color: 'warning', icon: 'mdi-cancel' },
  running: { label: 'Running…', color: 'primary', icon: 'mdi-progress-clock' },
  queued: { label: 'Queued', color: 'grey', icon: 'mdi-timer-sand' },
}
