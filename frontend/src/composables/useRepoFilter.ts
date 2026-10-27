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

import { computed, ref, watch, type Ref } from 'vue'
import type { TreeData } from '@/types/dashboard'

/**
 * Narrows the code map to the repositories the user picked. Every repo is
 * visible until the user narrows it, and a repo set change (one added or
 * removed) resets the pick to all.
 */
export function useRepoFilter(treeData: Ref<TreeData | null>) {
  const visibleRepos = ref<string[]>([])
  const repoNames = computed(() => treeData.value?.repos.map(r => r.repo_name) ?? [])

  watch(repoNames, names => {
    if (names.length > 0 && (visibleRepos.value.length === 0
      || !visibleRepos.value.every(r => names.includes(r)))) {
      visibleRepos.value = [...names]
    }
  }, { immediate: true })

  const displayData = computed<TreeData | null>(() => {
    const data = treeData.value
    if (!data) return null
    if (visibleRepos.value.length === repoNames.value.length) return data

    const visible = new Set(visibleRepos.value)
    const repos = data.repos.filter(r => visible.has(r.repo_name))
    const branches = new Set(repos.flatMap(r => r.branches.map(b => b.name)))
    const inScope = (repo: string | null, branch: string | null): boolean =>
      repo ? visible.has(repo) : !branch || branches.has(branch)

    const features = data.features.filter(f => inScope(f.repo_name, f.branch_name))
    return {
      ...data,
      repos,
      branches: repos.flatMap(r => r.branches),
      features,
      // The backend sends one row per repo a feature touches (for the
      // cross-repo arcs); the total counts each feature once.
      total_features: new Set(features.map(f => f.title)).size,
      buds: data.buds.filter(b => inScope(b.repo_name, b.branch_name)),
      threats: data.threats.filter(t => !t.branch_name || branches.has(t.branch_name)),
      relationships: (data.relationships ?? []).filter(r =>
        visible.has(r.source_repo) && visible.has(r.target_repo)),
    }
  })

  function toggleAll(): void {
    visibleRepos.value = visibleRepos.value.length === repoNames.value.length ? [] : [...repoNames.value]
  }

  return { visibleRepos, repoNames, displayData, toggleAll }
}
