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
