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
 * Real-time yield-offer subscription via WebSocket.
 *
 * Subscribes to ``yield_offer:{userId}`` and pushes incoming events
 * into the Pinia store. Re-fetches on every WS reconnect (events fired
 * during the dropped-socket window aren't replayed) and on tab
 * visibility change (cross-tab consistency: if Tab A accepts an offer,
 * Tab B's badge must drop on focus return).
 */
import { onMounted, onUnmounted } from 'vue'
import { subscribe, unsubscribe } from '@/services/socket'
import { onSocketReconnect } from '@/services/wsReconnect'
import { useYieldOfferStore } from '@/stores/yieldOffers'
import type { YieldOfferSocketEvent } from '@/types'

export function useYieldOfferSocket(userId: string): void {
  const store = useYieldOfferStore()
  const topic = `yield_offer:${userId}`

  const handler = (data: unknown) => {
    store.applySocketEvent(data as YieldOfferSocketEvent)
  }

  subscribe(topic, handler)
  const unregisterReconnect = onSocketReconnect(() => store.fetchPending())

  const onVisibility = () => {
    if (document.visibilityState === 'visible') {
      store.fetchPending()
    }
  }

  onMounted(() => {
    document.addEventListener('visibilitychange', onVisibility)
  })

  onUnmounted(() => {
    unsubscribe(topic, handler)
    unregisterReconnect()
    document.removeEventListener('visibilitychange', onVisibility)
  })
}
