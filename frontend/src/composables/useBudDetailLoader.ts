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

// Loads the BUD named in the route and keeps it live. Runs on first mount
// and again on every move between BUDs, because the router reuses the
// page component for /buds/A → /buds/B.

import { watch, type ComputedRef, type Ref } from 'vue'
import { useRoute } from 'vue-router'
import { useBUDStore } from '@/stores/bud'
import { useMembersStore } from '@/stores/members'
import { useSettingsStore } from '@/stores/settings'
import { useBudActivityChannel } from '@/composables/useBudActivityChannel'
import { VALID_BUD_TABS, type BUDDocument } from '@/types'
import { STATUS_TAB_MAP } from '@/utils/budDetail'

export interface BudLoaderHooks {
  bud: ComputedRef<BUDDocument | null>
  activeTab: Ref<string>
  startNewSession: () => void
  loadChatHistory: () => Promise<void>
  loadTimeline: () => Promise<void>
  reloadEstimates: () => void
  onLearningRecorded: () => void
}

export function useBudDetailLoader(hooks: BudLoaderHooks) {
  const route = useRoute()
  const budStore = useBUDStore()
  const membersStore = useMembersStore()
  const settingsStore = useSettingsStore()

  const channel = useBudActivityChannel({
    refresh: (id) => {
      // The guarded refresh no-ops if the user has moved to another BUD.
      void budStore.refreshBUDIfCurrent(id)
      void hooks.loadTimeline()
      hooks.reloadEstimates()
    },
    onLearningRecorded: hooks.onLearningRecorded,
  })

  // Each load takes a ticket; a load that a newer one has overtaken stops
  // at its next await, so it can't set the tab or connect a stale channel.
  let loadSeq = 0

  async function loadBud(id: string): Promise<void> {
    const seq = ++loadSeq
    const stale = () => seq !== loadSeq
    channel.disconnect()
    hooks.startNewSession()
    const tabParam = route.query.tab as string | undefined
    if (tabParam && VALID_BUD_TABS.has(tabParam)) hooks.activeTab.value = tabParam
    await budStore.fetchBUD(id)
    if (stale()) return
    const bud = hooks.bud.value
    if (!tabParam && bud) hooks.activeTab.value = STATUS_TAB_MAP[bud.status] ?? hooks.activeTab.value
    await hooks.loadChatHistory()
    if (stale()) return
    membersStore.fetchMembers()
    void hooks.loadTimeline()
    // UAT visibility and the release tabs' branch links read these.
    if (!settingsStore.connectionsLoaded) settingsStore.fetchConnections()
    if (settingsStore.repos.length === 0) settingsStore.fetchRepos()
    channel.connect(id)
  }

  /** Load the route's BUD again, e.g. after a failed load. */
  function reload(): void {
    const id = route.params.id as string
    if (id) void loadBud(id)
  }

  watch(() => route.params.id as string, (id) => { if (id) void loadBud(id) }, { immediate: true })

  return { reload }
}
