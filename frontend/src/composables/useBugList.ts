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
 * Loading and filters for the Bugs page.
 *
 * ``?scope=production|testing|all`` picks the environment. ``?budId=<id>``
 * (the BUD board links here from a card's bug count) lists that BUD's bugs
 * from the BUD-filtered list endpoint instead of the board, across both
 * environments unless a scope is given. ``?featureId=<id>`` narrows the
 * board to one feature.
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useBUDStore } from '@/stores/bud'
import { useBugsStore } from '@/stores/bugs'
import type { BugSeverity } from '@/types'
import {
  budFilterLabel,
  filterBugs,
  flattenBoard,
  isScope,
  openCount,
  type BugScope,
  type BugStatusGroup,
} from '@/utils/bugList'

// The list endpoint's page-size ceiling; a BUD rarely has more bugs.
const BUD_BUGS_PAGE = 100

function queryString(value: unknown): string | null {
  return typeof value === 'string' && value ? value : null
}

export function useBugList() {
  const bugsStore = useBugsStore()
  const budStore = useBUDStore()
  const route = useRoute()
  const router = useRouter()

  const budId = computed(() => queryString(route.query.budId))
  const featureId = computed(() => queryString(route.query.featureId))
  const scope = computed<BugScope>({
    get: () => (isScope(route.query.scope) ? route.query.scope : budId.value ? 'all' : 'production'),
    set: value => void router.replace({ query: { ...route.query, scope: value } }),
  })
  const severity = ref<BugSeverity | null>(null)
  const status = ref<BugStatusGroup | null>('open')

  const loading = computed(() => (budId.value ? bugsStore.loading : bugsStore.boardLoading))
  // Everything loaded for the current environment and BUD, before the
  // severity and status filters.
  const loaded = computed(() => {
    const all = budId.value ? bugsStore.bugs : flattenBoard(bugsStore.board)
    return filterBugs(all, { scope: scope.value, severity: null, status: null })
  })
  const rows = computed(() => filterBugs(loaded.value, { scope: 'all', severity: severity.value, status: status.value }))
  const open = computed(() => openCount(loaded.value))
  const filtering = computed(() => severity.value !== null || status.value !== 'open')
  const budLabel = computed(() => (budId.value ? budFilterLabel(budId.value, budStore.buds, bugsStore.bugs) : ''))

  async function load(): Promise<void> {
    if (budId.value) {
      await bugsStore.fetchBugs({ budId: budId.value, pageSize: BUD_BUGS_PAGE, page: 1 })
    } else {
      await bugsStore.fetchBoard({ bugType: scope.value, featureId: featureId.value ?? undefined })
    }
  }

  function clearBud(): void {
    void router.replace({ query: { ...route.query, budId: undefined } })
  }

  watch([budId, featureId, () => (budId.value ? null : scope.value)], () => void load(), { immediate: true })

  return { bugsStore, scope, severity, status, budId, budLabel, loading, loaded, rows, open, filtering, load, clearBud }
}
