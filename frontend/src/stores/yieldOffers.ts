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

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'
import { useBUDStore } from '@/stores/bud'
import type { YieldOffer, YieldOfferSocketEvent } from '@/types'

/** Pinia store for the current user's pending yield offers.
 *
 *  Drives the board notice (``YieldOfferNotice``) AND the nav badge.
 *  Backend TTL-on-read means anything we ``fetchPending()`` is
 *  guaranteed live (overdue rows are flipped to expired before the
 *  response builds). WS pushes new offers via ``addFromSocket`` and
 *  removes accepted/rejected/expired ones via ``removeFromSocket``. */
export const useYieldOfferStore = defineStore('yieldOffers', () => {
  const items = ref<YieldOffer[]>([])
  const loading = ref(false)
  const error = ref('')
  // Remember the scope the consumer requested so WS / reconnect /
  // visibility refetches don't silently degrade an admin's org-wide
  // view to a personal one. Set on every successful fetchPending().
  const lastScope = ref<'me' | 'org'>('me')

  const pendingCount = computed(
    () => items.value.filter(o => o.status === 'pending').length,
  )

  async function fetchPending(scope: 'me' | 'org' = lastScope.value): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.get<YieldOffer[]>('/v1/yield-offers', { params: { scope } })
      items.value = data
      lastScope.value = scope
    } catch {
      error.value = 'Failed to load yield offers'
    } finally {
      loading.value = false
    }
  }

  async function reassign(offerId: string, targetUserId: string): Promise<boolean> {
    error.value = ''
    try {
      const { data } = await api.post<YieldOffer>(
        `/v1/yield-offers/${offerId}/reassign`,
        { target_user_id: targetUserId },
      )
      // Swap the row in-place so the admin board updates without a refetch.
      const idx = items.value.findIndex(o => o.id === offerId)
      if (idx !== -1) items.value[idx] = data
      return true
    } catch {
      error.value = 'Failed to reassign yield offer'
      return false
    }
  }

  /** Re-pull the BUD list so the board kanban reflects the new
   *  assignments (assignee swap on accept, no-op on reject but cheap).
   *  Lazily imports the BUD store to avoid an init-order coupling. */
  async function refreshBUDBoard(): Promise<void> {
    await useBUDStore().fetchBUDs()
  }

  async function accept(offerId: string): Promise<boolean> {
    error.value = ''
    try {
      await api.post(`/v1/yield-offers/${offerId}/accept`)
      items.value = items.value.filter(o => o.id !== offerId)
      // Accept moves assignment between two BUDs — the board MUST
      // refetch or the kanban shows stale assignees until refresh.
      await refreshBUDBoard()
      return true
    } catch {
      error.value = 'Failed to accept yield offer'
      return false
    }
  }

  async function reject(offerId: string): Promise<boolean> {
    error.value = ''
    try {
      await api.post(`/v1/yield-offers/${offerId}/reject`)
      items.value = items.value.filter(o => o.id !== offerId)
      return true
    } catch {
      error.value = 'Failed to reject yield offer'
      return false
    }
  }

  /** Handle a ``yield_offer:{userId}`` WS push. ``created`` triggers a
   *  refetch (we need the hydrated bud number/title/priority that only
   *  the API can join); ``resolved`` drops the local row in place so
   *  the notice + badge update without a round-trip. In both cases
   *  we also re-pull the BUD board because the event implies an
   *  assignee change somewhere — admin reassign, a peer's accept on
   *  another tab, etc. */
  function applySocketEvent(evt: YieldOfferSocketEvent): void {
    if (evt.event === 'created') {
      void fetchPending()
      void refreshBUDBoard()
      return
    }
    if (evt.event === 'resolved') {
      items.value = items.value.filter(o => o.id !== evt.offer_id)
      void refreshBUDBoard()
    }
  }

  return {
    items,
    loading,
    error,
    pendingCount,
    fetchPending,
    accept,
    reject,
    reassign,
    applySocketEvent,
  }
})
