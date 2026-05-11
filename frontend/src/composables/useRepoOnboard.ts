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
 * Selection + branch-pick + submission state for the bulk-import tab.
 *
 * Owns transient UI state only — all HTTP traffic flows through
 * ``useRepoOnboardStore``. Pure helpers (canSubmit predicate, item
 * builder, branch-pick reducer) live in ``useRepoOnboard.types.ts``
 * so this file stays under the project's line cap.
 */

import { computed, reactive, ref } from 'vue'
import { useRepoOnboardStore } from '@/stores/repoOnboard'
import {
  type AppInstallState,
  type BranchPick,
  type BulkOnboardJobCreated,
  type InstallableRepo,
} from '@/types/repoOnboard'
import {
  applyBranchPick,
  buildSubmitItems,
  detectDevelopBranch,
  isReadyToSubmit,
  type BranchKind,
} from '@/composables/useRepoOnboard.types'

export interface UseRepoOnboardOptions {
  /** Override the store (unit tests). Production uses Pinia singleton. */
  store?: ReturnType<typeof useRepoOnboardStore>
}

export function useRepoOnboard(options: UseRepoOnboardOptions = {}) {
  const store = options.store ?? useRepoOnboardStore()

  const installable = ref<InstallableRepo[]>([])
  const appInstallState = ref<AppInstallState | null>(null)
  const installUrl = ref<string | null>(null)

  const selection = ref<Set<string>>(new Set())
  const branchesByRepo = reactive<Map<string, BranchPick>>(new Map())
  const branchOptions = reactive<Map<string, string[]>>(new Map())

  const loadingInstallable = ref(false)
  const loadingBranchesFor = reactive<Set<string>>(new Set())
  const submitting = ref(false)
  const errorMessage = ref<string | null>(null)

  const installableByName = computed(() => {
    const map = new Map<string, InstallableRepo>()
    for (const repo of installable.value) {
      map.set(repo.fullName, repo)
    }
    return map
  })

  const selectedRepos = computed<InstallableRepo[]>(() => {
    const out: InstallableRepo[] = []
    for (const fullName of selection.value) {
      const repo = installableByName.value.get(fullName)
      if (repo) out.push(repo)
    }
    return out
  })

  const selectionCount = computed(() => selection.value.size)
  const canSubmit = computed(() => isReadyToSubmit(selection.value, branchesByRepo))

  async function loadInstallable(): Promise<void> {
    loadingInstallable.value = true
    errorMessage.value = null
    try {
      const result = await store.loadInstallableRepos()
      if (!result) {
        errorMessage.value = store.lastError
        return
      }
      installable.value = result.repos
      appInstallState.value = result.appInstallState
      installUrl.value = result.installUrl
    } finally {
      loadingInstallable.value = false
    }
  }

  async function loadBranchesFor(fullName: string, force = false): Promise<void> {
    if (!force && branchOptions.has(fullName)) return
    if (loadingBranchesFor.has(fullName)) return
    loadingBranchesFor.add(fullName)
    try {
      const branches = await store.loadInstallableBranches(fullName)
      if (!branches) {
        errorMessage.value = store.lastError
        return
      }
      branchOptions.set(fullName, branches)
      const repo = installableByName.value.get(fullName)
      const existing = branchesByRepo.get(fullName)
      if (!existing && repo && branches.includes(repo.defaultBranch)) {
        const detectedDevelop = detectDevelopBranch(branches, repo.defaultBranch)
        branchesByRepo.set(fullName, {
          main: repo.defaultBranch,
          develop: detectedDevelop,
        })
      }
    } finally {
      loadingBranchesFor.delete(fullName)
    }
  }

  function refreshBranchesFor(fullName: string): Promise<void> {
    return loadBranchesFor(fullName, true)
  }

  function toggleSelection(fullName: string): Promise<void> {
    const next = new Set(selection.value)
    if (next.has(fullName)) {
      next.delete(fullName)
      branchesByRepo.delete(fullName)
      selection.value = next
      return Promise.resolve()
    }
    next.add(fullName)
    selection.value = next
    return loadBranchesFor(fullName)
  }

  function selectAllForOwner(ownerLogin: string, select: boolean): Promise<void> {
    const next = new Set(selection.value)
    const pending: Promise<void>[] = []
    for (const repo of installable.value) {
      if (repo.ownerLogin !== ownerLogin || repo.alreadyTracked) continue
      if (select) {
        if (!next.has(repo.fullName)) {
          next.add(repo.fullName)
          pending.push(loadBranchesFor(repo.fullName))
        }
      } else {
        next.delete(repo.fullName)
        branchesByRepo.delete(repo.fullName)
      }
    }
    selection.value = next
    return Promise.all(pending).then(() => undefined)
  }

  function setBranchPick(fullName: string, kind: BranchKind, branch: string | null): void {
    branchesByRepo.set(fullName, applyBranchPick(branchesByRepo.get(fullName), kind, branch))
  }

  async function submitBulkOnboard(): Promise<BulkOnboardJobCreated | null> {
    if (!canSubmit.value) return null
    submitting.value = true
    errorMessage.value = null
    try {
      const items = buildSubmitItems(selection.value, branchesByRepo)
      const result = await store.submitBulkOnboard({ items })
      if (!result) {
        errorMessage.value = store.lastError
        return null
      }
      return result
    } finally {
      submitting.value = false
    }
  }

  function reset(): void {
    selection.value = new Set()
    branchesByRepo.clear()
    errorMessage.value = null
  }

  return {
    installable,
    appInstallState,
    installUrl,
    selection,
    branchesByRepo,
    branchOptions,
    loadingInstallable,
    loadingBranchesFor,
    submitting,
    errorMessage,
    selectedRepos,
    selectionCount,
    canSubmit,
    loadInstallable,
    loadBranchesFor,
    refreshBranchesFor,
    toggleSelection,
    selectAllForOwner,
    setBranchPick,
    submitBulkOnboard,
    reset,
  }
}

export type UseRepoOnboardReturn = ReturnType<typeof useRepoOnboard>
