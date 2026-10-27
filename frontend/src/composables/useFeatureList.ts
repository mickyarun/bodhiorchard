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
 * Filters, paging and loading for the Features page.
 *
 * ``?id=<uuid>`` (a BUD's linked-feature row deep-links here) shows that one
 * feature on its own; clearing it drops the param and the listing reloads.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PAGE_SIZE, useFeaturesStore, type FeatureViewMode } from '@/stores/features'
import { useSettingsStore } from '@/stores/settings'
import type { RepoContributor } from '@/types'
import { useDebounced } from './useDebounced'

export function useFeatureList() {
  const store = useFeaturesStore()
  const settingsStore = useSettingsStore()
  const route = useRoute()
  const router = useRouter()

  const repoId = ref('')
  const query = ref('')
  const debouncedQuery = useDebounced(computed(() => query.value.trim()))
  const mode = ref<FeatureViewMode>('active')
  const touchedSort = ref<'asc' | 'desc'>('desc')
  const page = ref(1)
  const hasLoadedOnce = ref(false)
  const focusedId = ref<string | null>(null)

  const activeRepos = computed(() => settingsStore.repos.filter(r => r.status !== 'removed'))
  const pageCount = computed(() => Math.max(1, Math.ceil(store.total / PAGE_SIZE)))
  const filtering = computed(() => !!repoId.value || !!debouncedQuery.value)
  // Nothing mapped at all, as opposed to nothing matching the filters.
  const nothingMapped = computed(
    () => store.items.length === 0 && !filtering.value && !focusedId.value && (mode.value === 'active' || mode.value === 'all'),
  )

  const contributors = computed<RepoContributor[]>(() => store.contributorsByRepo[repoId.value] ?? [])
  const contributorsLoading = computed(() => !!repoId.value && !(repoId.value in store.contributorsByRepo))

  async function reload(): Promise<void> {
    await store.fetchPage({
      page: page.value,
      repoId: repoId.value || undefined,
      q: debouncedQuery.value || undefined,
      mode: mode.value,
      touchedSort: touchedSort.value,
    })
    if (repoId.value) void store.fetchTopContributors(repoId.value)
    hasLoadedOnce.value = true
  }

  // Filter changes go back to page 1; the page watcher does the reload.
  watch([repoId, debouncedQuery, mode, touchedSort], () => {
    if (page.value === 1) void reload()
    else page.value = 1
  })
  watch(page, () => void reload())

  async function loadFocused(id: string): Promise<void> {
    focusedId.value = id
    await store.fetchFeature(id)
    store.items = store.selectedFeature ? [store.selectedFeature] : []
    store.total = store.items.length
    hasLoadedOnce.value = true
  }

  function clearFocus(): void {
    void router.replace({ query: { ...route.query, id: undefined } })
  }

  watch(
    () => route.query.id,
    async next => {
      if (typeof next === 'string' && next) {
        await loadFocused(next)
      } else if (focusedId.value != null) {
        focusedId.value = null
        await reload()
      }
    },
  )

  onMounted(async () => {
    void settingsStore.fetchRepos()
    const initial = route.query.id
    if (typeof initial === 'string' && initial) await loadFocused(initial)
    else void reload()
  })

  return {
    store, repoId, query, mode, touchedSort, page, pageCount, hasLoadedOnce, focusedId,
    activeRepos, filtering, nothingMapped, contributors, contributorsLoading, clearFocus, reload,
  }
}
