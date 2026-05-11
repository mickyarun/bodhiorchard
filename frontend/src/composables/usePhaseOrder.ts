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

import { computed, type ComputedRef } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { BUD_STATUS_ORDER, type BUDStatus } from '@/types'

/**
 * Single source of truth for the BUD lifecycle phase order as it applies
 * to the current org. Filters BUD_STATUS_ORDER based on the org's
 * bud_stages settings (e.g. uat_enabled=false removes "uat" from the list).
 *
 * Every component that renders a phase dropdown, phase timeline, or phase
 * label list should import from here rather than referencing BUD_STATUS_ORDER
 * directly — otherwise the UAT toggle will silently fail to hide UAT in
 * that component. BUD_STATUS_ORDER stays as the canonical unfiltered list
 * for type-union purposes (it contains every possible status including
 * "closed" and "discarded") and should only be read by code that truly
 * wants every status regardless of org settings.
 *
 * Returns a reactive computed ref — toggling the UAT setting in the
 * store (via PATCH /settings/connections) updates every component that
 * uses this composable, without needing a page reload.
 */
export function usePhaseOrder(): { phaseOrder: ComputedRef<BUDStatus[]> } {
  const settingsStore = useSettingsStore()
  const phaseOrder = computed<BUDStatus[]>(() => {
    // Default to UAT enabled when settings haven't loaded yet — matches
    // backend default and avoids a brief flash where UAT is missing
    // during the initial /settings/connections fetch.
    const uatEnabled = settingsStore.connections.budStages?.uatEnabled ?? true
    if (uatEnabled) return BUD_STATUS_ORDER
    return BUD_STATUS_ORDER.filter((s) => s !== 'uat')
  })
  return { phaseOrder }
}
