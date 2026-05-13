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
 * Status-transition orchestration for the BUD detail page.
 *
 * Owns the guard logic (code_review → testing PR-merge check, testing
 * → uat/prod manual-cases check, no-open-PR warning for entering code
 * review), the three guard dialogs' state, the running-status banner,
 * the snackbar surfacing backend rejections, and the cancel-running-
 * agent handler.
 *
 * Cross-cutting view dependencies (active tab switching, design-
 * generation trigger, timeline reload) come in as hooks; the
 * composable doesn't reach into view-only refs directly.
 */

import { nextTick, ref } from 'vue'
import { useBUDStore } from '@/stores/bud'
import type { BUDDocument } from '@/types'

export interface BudStatusHooks {
  /** Current BUD; null while the page is still loading. */
  getBud: () => BUDDocument | null
  /** Switch the page's active tab — used by openQATab and the post-
   *  success tab sync after a successful PATCH. */
  setActiveTab: (tab: string) => void
  /** Status → tab mapping owned by the view (single source of truth
   *  for tab routing across multiple watchers). */
  getStatusTabMap: () => Record<string, string>
  /** Open the design-generation flow when entering the design phase. */
  triggerDesignGeneration: () => void | Promise<void>
  /** Refresh the timeline after a successful transition. */
  reloadTimeline: () => Promise<void>
}

export const PHASE_ROLE_LABELS: Record<string, string> = {
  bud: 'product manager',
  design: 'designer',
  tech_arch: 'tech lead',
  development: 'developer',
  code_review: 'developer',
  testing: 'QA engineer',
  uat: 'product manager',
}

export function useBudStatusTransitions(hooks: BudStatusHooks) {
  const budStore = useBUDStore()

  // In-flight banner
  const statusChanging = ref(false)
  const statusChangeTarget = ref('')

  // Guard dialogs
  const showNoPRWarningDialog = ref(false)
  const overrideReasonDialog = ref(false)
  const overrideReasonText = ref('')
  const pendingOverrideStatus = ref('')
  const showPendingCasesDialog = ref(false)
  const pendingCasesTarget = ref('')
  const pendingCasesList = ref<{ id: string; title: string }[]>([])

  // Backend rejection surface
  const statusErrorSnackbar = ref(false)
  const statusErrorMessage = ref('')

  // Cancel agent task running in this phase
  const cancellingAgent = ref(false)

  async function cancelRunningAgent(): Promise<void> {
    const bud = hooks.getBud()
    const taskId = bud?.active_agent_task?.id
    if (!taskId || !bud) return
    cancellingAgent.value = true
    try {
      await budStore.cancelAgentTask(bud.id, taskId)
    } finally {
      cancellingAgent.value = false
    }
  }

  async function updateStatus(newStatus: string): Promise<void> {
    const bud = hooks.getBud()
    if (!bud) return

    // Intercept code_review transition: warn if no PRs are open.
    if (newStatus === 'code_review') {
      const repoStatuses = await budStore.fetchCodeReviewStatus(bud.id)
      const hasOpenPR = repoStatuses.some(r => r.pr_state === 'open')
      if (!hasOpenPR) {
        showNoPRWarningDialog.value = true
        return
      }
    }

    // Manual advance code_review → testing:
    //   - If every impacted repo already has a merged PR, there's nothing to
    //     "override" — the code is approved on GitHub and we just advance
    //     straight through, same outcome as the webhook auto-transition.
    //   - Otherwise the user is bypassing PR merges (e.g. docs-only change
    //     or unusual workflow), so we still prompt for a reason so the
    //     bypass is recorded on the timeline.
    if (bud.status === 'code_review' && newStatus === 'testing') {
      const repoStatuses = await budStore.fetchCodeReviewStatus(bud.id)
      const allMerged = repoStatuses.length > 0
        && repoStatuses.every(r => r.pr_state === 'merged')
      if (!allMerged) {
        pendingOverrideStatus.value = newStatus
        overrideReasonText.value = ''
        overrideReasonDialog.value = true
        return
      }
    }

    // Guard: testing → uat (or → prod when UAT is disabled) must have
    // every manual test case in a terminal state. Preempt the backend
    // guard client-side so the user sees the list of blocking cases in
    // a modal instead of hitting a 400 and seeing a snackbar. The
    // backend guard still fires as the authoritative check.
    //
    // Re-fetch the BUD first so qa_manual_cases reflects results saved
    // in the QA tab. The test runner composable (useQATestCases)
    // updates its own local ref but doesn't refresh the store's
    // currentBUD, so bud.qa_manual_cases can be stale after marking
    // cases as pass.
    if (bud.status === 'testing' && (newStatus === 'uat' || newStatus === 'prod')) {
      await budStore.fetchBUD(bud.id)
      const refreshed = hooks.getBud()
      const pending = (refreshed?.qa_manual_cases ?? []).filter(
        tc => tc.result === 'pending',
      )
      if (pending.length > 0) {
        pendingCasesTarget.value = newStatus
        pendingCasesList.value = pending.map(tc => ({ id: tc.id, title: tc.title }))
        showPendingCasesDialog.value = true
        return
      }
    }

    await executeStatusChange(newStatus)
  }

  function openQATab(): void {
    showPendingCasesDialog.value = false
    hooks.setActiveTab('testing')
  }

  async function confirmNoPRWarning(): Promise<void> {
    showNoPRWarningDialog.value = false
    await executeStatusChange('code_review')
  }

  async function confirmOverrideStatus(): Promise<void> {
    const reason = overrideReasonText.value.trim()
    if (!reason) return
    overrideReasonDialog.value = false
    await executeStatusChange(pendingOverrideStatus.value, reason)
  }

  async function executeStatusChange(newStatus: string, reason?: string): Promise<void> {
    const bud = hooks.getBud()
    if (!bud) return
    statusChangeTarget.value = newStatus
    statusChanging.value = true
    try {
      const payload: Record<string, unknown> = { status: newStatus }
      if (reason) payload.status_override_reason = reason
      const result = await budStore.updateBUD(bud.id, payload as never)
      // When the store returns null, the backend rejected the PATCH.
      // The store has already captured the detail string into
      // budStore.error via extractApiError — surface it in the
      // snackbar so the user sees exactly why (e.g. the backend
      // manual-cases guard catching a race the client-side preempt
      // missed).
      if (result === null && budStore.error) {
        statusErrorMessage.value = budStore.error
        statusErrorSnackbar.value = true
        return
      }
    } finally {
      statusChanging.value = false
    }

    // Switch tab to match the new status phase.
    const targetTab = hooks.getStatusTabMap()[newStatus]
    if (targetTab) hooks.setActiveTab(targetTab)

    // If entering design phase, open repo picker for generation.
    if (budStore.designAvailable) {
      budStore.designAvailable = false
      await nextTick()
      await hooks.triggerDesignGeneration()
    }

    await hooks.reloadTimeline()
  }

  return {
    // banner state
    statusChanging,
    statusChangeTarget,
    cancellingAgent,
    // guard-dialog state
    showNoPRWarningDialog,
    overrideReasonDialog,
    overrideReasonText,
    showPendingCasesDialog,
    pendingCasesTarget,
    pendingCasesList,
    // snackbar state
    statusErrorSnackbar,
    statusErrorMessage,
    // actions
    cancelRunningAgent,
    updateStatus,
    openQATab,
    confirmNoPRWarning,
    confirmOverrideStatus,
  }
}
