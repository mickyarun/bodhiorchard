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

// Whether any repo this BUD touches has a UAT or production branch set.
// Without one the release-stage tabs offer a "configure branch" link.
// Branches live on the settings store's repo list, not on the BUD.

import { computed, type ComputedRef } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import type { BUDDocument } from '@/types'

export function useBudReleaseBranches(bud: ComputedRef<BUDDocument | null>) {
  const settingsStore = useSettingsStore()
  const touchedRepos = computed(() => {
    const ids = new Set((bud.value?.impacted_repos ?? []).map(r => r.repo_id))
    return settingsStore.repos.filter(r => ids.has(r.id))
  })
  const hasUatBranchConfigured = computed(() => touchedRepos.value.some(r => !!r.uatBranch))
  const hasMainBranchConfigured = computed(() => touchedRepos.value.some(r => !!r.mainBranch))
  return { hasUatBranchConfigured, hasMainBranchConfigured }
}
