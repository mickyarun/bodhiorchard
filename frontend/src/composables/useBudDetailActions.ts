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

// Edits made from the BUD detail page's header and side panels. Each one
// reloads the timeline afterwards so its event shows straight away.

import type { ComputedRef } from 'vue'
import { useRouter } from 'vue-router'
import { useBUDStore } from '@/stores/bud'
import type { BUDDocument, BUDPriority } from '@/types'

export function useBudDetailActions(bud: ComputedRef<BUDDocument | null>, loadTimeline: () => Promise<void>) {
  const budStore = useBUDStore()
  const router = useRouter()

  /** Background refresh; no-ops if the user has moved to another BUD meanwhile. */
  async function refreshBudAndTimeline(): Promise<void> {
    if (!bud.value) return
    await Promise.all([budStore.refreshBUDIfCurrent(bud.value.id), loadTimeline()])
  }

  async function refreshAfterSettingsSave(): Promise<void> {
    if (!bud.value) return
    try {
      await budStore.refreshBUDIfCurrent(bud.value.id)
    } catch (err) {
      // A failed refetch leaves the banner stale until a reload; say so.
      console.error('BUD reload after settings save failed:', err)
    }
  }

  async function saveTitle(title: string): Promise<void> {
    if (!bud.value) return
    await budStore.updateBUD(bud.value.id, { title })
    await loadTimeline()
  }

  async function changeAssignee(memberId: string | null): Promise<void> {
    if (!bud.value) return
    await budStore.updateBUD(bud.value.id, { assignee_id: memberId } as never)
    await loadTimeline()
  }

  async function changePriority(priority: BUDPriority): Promise<void> {
    if (!bud.value || bud.value.priority === priority) return
    await budStore.updateBUD(bud.value.id, { priority } as never)
    await loadTimeline()
  }

  async function deleteBud(): Promise<void> {
    if (bud.value && (await budStore.deleteBUD(bud.value.id))) void router.push('/buds')
  }

  return { refreshBudAndTimeline, refreshAfterSettingsSave, saveTitle, changeAssignee, changePriority, deleteBud }
}
