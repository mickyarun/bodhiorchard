// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
