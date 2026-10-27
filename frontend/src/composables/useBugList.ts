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
  BOARD_LIMIT,
  BUD_LIST_LIMIT,
  budFilterLabel,
  filterBugs,
  flattenBoard,
  isScope,
  openCount,
  truncationNote,
  type BugScope,
  type BugStatusGroup,
} from '@/utils/bugList'

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

  // Which list the store holds. Until a load for the current BUD (or
  // environment) finishes, rows from the previous one aren't shown.
  const wantedKey = computed(() => (budId.value ? `bud:${budId.value}` : `board:${scope.value}:${featureId.value ?? ''}`))
  const loadedKey = ref<string | null>(null)
  const current = computed(() => loadedKey.value === wantedKey.value)

  const loading = computed(() => (budId.value ? bugsStore.loading : bugsStore.boardLoading))
  const loadError = computed(() => bugsStore.loadError)
  // Everything loaded for the current environment and BUD, before the
  // severity and status filters.
  const fetched = computed(() => {
    if (!current.value) return []
    return budId.value ? bugsStore.bugs : flattenBoard(bugsStore.board)
  })
  const loaded = computed(() => filterBugs(fetched.value, { scope: scope.value, severity: null, status: null }))
  const rows = computed(() => filterBugs(loaded.value, { scope: 'all', severity: severity.value, status: status.value }))
  const open = computed(() => openCount(loaded.value))
  const filtering = computed(() => severity.value !== null || status.value !== 'open')
  const budLabel = computed(() => (budId.value ? budFilterLabel(budId.value, budStore.buds, bugsStore.bugs) : ''))
  const truncated = computed(() =>
    budId.value
      ? truncationNote(fetched.value.length, bugsStore.total, BUD_LIST_LIMIT)
      : truncationNote(fetched.value.length, null, BOARD_LIMIT),
  )

  async function load(): Promise<void> {
    const key = wantedKey.value
    if (budId.value) {
      await bugsStore.fetchBugs({ budId: budId.value, pageSize: BUD_LIST_LIMIT, page: 1 })
    } else {
      await bugsStore.fetchBoard({ bugType: scope.value, featureId: featureId.value ?? undefined })
    }
    // A slower earlier load must not mark a newer list as loaded.
    if (key === wantedKey.value && !bugsStore.loadError) loadedKey.value = key
  }

  function clearBud(): void {
    void router.replace({ query: { ...route.query, budId: undefined } })
  }

  watch(wantedKey, () => void load(), { immediate: true })

  return {
    bugsStore, scope, severity, status, budId, budLabel, loading, loadError, loaded, rows, open, filtering,
    truncated, load, clearBud,
  }
}
