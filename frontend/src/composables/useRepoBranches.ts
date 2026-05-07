// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Wraps the settings-store branch-mapping calls with the dialog-shaped
 * state the new code-settings page needs: which repo is being edited,
 * the discovered branch list, and the chosen main / develop / UAT
 * picks.
 *
 * Also drives the post-clone walkthrough: when the add-repo dialog
 * finishes a multi-clone with one or more newly-cloned-but-unmapped
 * repos, it hands the queue here via `openWalkthrough`. We open the
 * dialog once per queued repo and invoke `onComplete` when the queue
 * drains (or a `cancel` short-circuits it).
 *
 * Keeps async + ref state out of the dialog component so the dialog
 * stays a presentation layer.
 */

import { ref } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import type { RepoInfo } from '@/types'

export function useRepoBranches() {
  const settingsStore = useSettingsStore()

  const editing = ref<RepoInfo | null>(null)
  const branches = ref<string[]>([])
  const mainBranch = ref<string | null>(null)
  const developBranch = ref<string | null>(null)
  const uatBranch = ref<string | null>(null)
  const loading = ref<boolean>(false)
  const saving = ref<boolean>(false)
  const error = ref<string>('')

  // Walkthrough state — only populated when openWalkthrough is called.
  const walkthroughQueue = ref<RepoInfo[]>([])
  const onWalkthroughComplete = ref<((completed: boolean) => void) | null>(null)

  async function open(repo: RepoInfo): Promise<void> {
    editing.value = repo
    error.value = ''
    branches.value = []
    mainBranch.value = repo.mainBranch ?? null
    developBranch.value = repo.developBranch ?? null
    uatBranch.value = repo.uatBranch ?? null
    loading.value = true
    try {
      const list = await settingsStore.fetchRepoBranches(repo.id)
      if (list) {
        branches.value = list.branches
        if (!mainBranch.value) mainBranch.value = list.currentMain
        if (!developBranch.value) developBranch.value = list.currentDevelop
        if (!uatBranch.value) uatBranch.value = list.currentUat
      } else {
        error.value = settingsStore.error || 'Failed to load branches.'
      }
    } finally {
      loading.value = false
    }
  }

  function clearForm(): void {
    editing.value = null
    branches.value = []
    mainBranch.value = null
    developBranch.value = null
    uatBranch.value = null
    error.value = ''
  }

  /** Cancel the dialog. If a walkthrough is active, abort the rest of
   *  the queue too — once a user has declined to map one repo, nagging
   *  them through the remaining clones is worse than letting the
   *  per-row "Not mapped" chip surface them naturally. */
  function close(): void {
    const cb = onWalkthroughComplete.value
    walkthroughQueue.value = []
    onWalkthroughComplete.value = null
    clearForm()
    if (cb) cb(false)
  }

  /** Persist the picks. When walkthrough is active, advance to the
   *  next queued repo (without triggering a full close); when the queue
   *  drains, fire the completion callback. */
  async function save(): Promise<boolean> {
    if (!editing.value) return false
    saving.value = true
    error.value = ''
    try {
      const ok = await settingsStore.updateRepoBranches(
        editing.value.id,
        mainBranch.value,
        developBranch.value,
        uatBranch.value,
      )
      if (!ok) {
        error.value = settingsStore.error || 'Failed to save branch mapping.'
        return false
      }
    } finally {
      saving.value = false
    }
    if (walkthroughQueue.value.length > 0) {
      const next = walkthroughQueue.value.shift()
      if (next) {
        await open(next)
        return true
      }
    }
    const cb = onWalkthroughComplete.value
    onWalkthroughComplete.value = null
    clearForm()
    if (cb) cb(true)
    return true
  }

  /** Walk every repo in `repos` through the branch-mapping dialog in
   *  sequence. Calls `onComplete(true)` after the last save, or
   *  `onComplete(false)` if the user cancels mid-flight. */
  async function openWalkthrough(
    repos: RepoInfo[],
    onComplete?: (completed: boolean) => void,
  ): Promise<void> {
    if (repos.length === 0) {
      if (onComplete) onComplete(true)
      return
    }
    onWalkthroughComplete.value = onComplete ?? null
    walkthroughQueue.value = repos.slice(1)
    await open(repos[0])
  }

  return {
    // state
    editing,
    branches,
    mainBranch,
    developBranch,
    uatBranch,
    loading,
    saving,
    error,
    walkthroughQueue,
    // actions
    open,
    close,
    save,
    openWalkthrough,
  }
}
