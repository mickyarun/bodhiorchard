// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Setup-mode sync helper for ``RepoOnboardBulkTab.vue``.
 *
 * Mirrors the bulk picker's selection + branch picks into
 * ``setupStore.state.sourceCode.repos`` so the wizard's Continue button
 * (which calls ``submitFinalize``) finds an ``installableItems``-shaped
 * payload waiting for it. Legacy paste-URL entries — anything without a
 * ``gitHubFullName`` discriminator — are preserved untouched.
 *
 * Only active when ``mode === 'setup'``; settings mode is a no-op.
 */

import { watch } from 'vue'
import { useSetupStore } from '@/stores/setup'
import type { UseRepoOnboardReturn } from '@/composables/useRepoOnboard'
import type { SetupRepoConfig } from '@/types/setup'

export function useBulkTabSetupSync(
  onboard: UseRepoOnboardReturn,
  isSetupMode: () => boolean,
): void {
  const setupStore = useSetupStore()

  function sync(): void {
    if (!isSetupMode()) return
    const next: SetupRepoConfig[] = []
    for (const repo of onboard.selectedRepos.value) {
      const pick = onboard.branchesByRepo.get(repo.fullName)
      next.push({
        path: '',
        gitHubFullName: repo.fullName,
        mainBranch: pick?.main || repo.defaultBranch || null,
        developBranch: pick?.develop || null,
        source: 'bulk',
      })
    }
    const legacy = setupStore.state.sourceCode.repos.filter((r) => !r.gitHubFullName)
    setupStore.state.sourceCode.repos = [...legacy, ...next]
  }

  watch(
    () => [
      Array.from(onboard.selection.value),
      Array.from(onboard.branchesByRepo.entries()).map(
        ([k, v]) => `${k}:${v.main || ''}:${v.develop || ''}`,
      ),
    ],
    sync,
    { deep: true },
  )
}
