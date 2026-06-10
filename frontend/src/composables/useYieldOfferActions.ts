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
 * Shared state + actions for yield-offer accept / reject / reassign.
 *
 * The trigger UI (rows inside NotificationBell) and the confirmation
 * modals (YieldOfferDialogs, mounted layout-wide) need the same
 * pendingX / busy state. Module-level refs let both consumers read and
 * mutate one instance without going through Pinia — the alternative
 * would be a UI-only Pinia store, which carries more boilerplate than
 * the single shared dialog warrants.
 */

import { ref } from 'vue'
import { useYieldOfferStore } from '@/stores/yieldOffers'
import type { YieldOffer } from '@/types'

const busy = ref<string | null>(null)
const rejectDialogOpen = ref(false)
const pendingRejectId = ref<string | null>(null)
const reassignDialogOpen = ref(false)
const pendingReassign = ref<YieldOffer | null>(null)
const reassignTargetId = ref<string | null>(null)

export function useYieldOfferActions() {
  const yieldStore = useYieldOfferStore()

  async function onAccept(id: string): Promise<void> {
    busy.value = id
    await yieldStore.accept(id)
    busy.value = null
  }

  function askReject(id: string): void {
    pendingRejectId.value = id
    rejectDialogOpen.value = true
  }

  async function confirmReject(): Promise<void> {
    if (!pendingRejectId.value) return
    busy.value = pendingRejectId.value
    await yieldStore.reject(pendingRejectId.value)
    busy.value = null
    closeReject()
  }

  function closeReject(): void {
    rejectDialogOpen.value = false
    pendingRejectId.value = null
  }

  function askReassign(offer: YieldOffer): void {
    pendingReassign.value = offer
    reassignTargetId.value = null
    reassignDialogOpen.value = true
  }

  async function confirmReassign(): Promise<void> {
    if (!pendingReassign.value || !reassignTargetId.value) return
    busy.value = pendingReassign.value.id
    const ok = await yieldStore.reassign(pendingReassign.value.id, reassignTargetId.value)
    busy.value = null
    if (ok) closeReassign()
  }

  function closeReassign(): void {
    reassignDialogOpen.value = false
    pendingReassign.value = null
    reassignTargetId.value = null
  }

  return {
    busy,
    rejectDialogOpen,
    reassignDialogOpen,
    pendingReassign,
    reassignTargetId,
    onAccept,
    askReject,
    confirmReject,
    closeReject,
    askReassign,
    confirmReassign,
    closeReassign,
  }
}
