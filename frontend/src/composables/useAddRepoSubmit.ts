// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Post-add orchestration for the Add Repo dialog. Owns:
 *
 *   - The "Scan after adding" toggle.
 *   - Snapshot/diff of `settingsStore.repos` across the local-pick or
 *     clone runs, so we can surface the *newly-added* RepoInfo rows to
 *     the caller without coupling the dialog to the import internals.
 *   - The post-add follow-up: walk newly-cloned-but-unmapped repos
 *     through the branch-mapping dialog, then optionally start a v2
 *     scan from the master selection.
 *
 * Lives outside `useRepoImport` because that composable is purely about
 * the local-pick / clone HTTP runs; this one is the dialog's "what now"
 * after those runs return.
 */

import { ref } from 'vue'
import { useReposcanV2ScansStore } from '@/stores/reposcanv2Scans'
import { useSettingsStore } from '@/stores/settings'
import type { useRepoBranches } from '@/composables/useRepoBranches'
import type { useRepoImport } from '@/composables/useRepoImport'
import type { RepoInfo } from '@/types'

type ImportComposable = ReturnType<typeof useRepoImport>
type BranchesComposable = ReturnType<typeof useRepoBranches>

export interface AddRepoSubmitResult {
  /** True only when every queued item ended up `done`. Mirrors the
   *  per-item bookkeeping inside useRepoImport so the dialog can decide
   *  whether to close on this submit attempt. */
  allDone: boolean
  /** The RepoInfo rows that appeared in the settings-store between the
   *  pre-run snapshot and the post-run state. Empty when nothing new
   *  was added (e.g. all clones errored, or the user re-submitted a
   *  queue that was already done). */
  newlyAdded: RepoInfo[]
}

export function useAddRepoSubmit() {
  const settingsStore = useSettingsStore()
  const scanStore = useReposcanV2ScansStore()

  const scanAfterAdd = ref<boolean>(true)

  /** Drive the local or clone runner, then diff repos to find what landed. */
  async function submit(
    tab: 'local' | 'clone',
    imp: ImportComposable,
  ): Promise<AddRepoSubmitResult> {
    const before = new Set(settingsStore.repos.map(r => r.id))
    const allDone = tab === 'local' ? await imp.runLocal() : await imp.runClones()
    const newlyAdded = settingsStore.repos.filter(r => !before.has(r.id))
    return { allDone, newlyAdded }
  }

  /** After the dialog closes: walk unmapped clones through the branch
   *  dialog, then (optionally) kick off a v2 scan over the current
   *  selection. The walkthrough's completion callback is what triggers
   *  the scan, so the order is always: clone → map → scan. */
  async function afterDialogClose(
    newlyAdded: RepoInfo[],
    branches: BranchesComposable,
  ): Promise<void> {
    const unmapped = newlyAdded.filter(r => !r.mainBranch || !r.developBranch)

    const maybeStartScan = async (completed: boolean) => {
      if (!completed || !scanAfterAdd.value) return
      // The master selection drives `startScan`; if the new repos
      // weren't already selected, opt them in here so the user gets
      // what they explicitly asked for ("scan after adding").
      for (const r of newlyAdded) scanStore.selectedRepoIds.add(r.id)
      await scanStore.startScan()
    }

    if (unmapped.length === 0) {
      await maybeStartScan(true)
      return
    }

    await branches.openWalkthrough(unmapped, (completed) => {
      void maybeStartScan(completed)
    })
  }

  return {
    scanAfterAdd,
    submit,
    afterDialogClose,
  }
}
