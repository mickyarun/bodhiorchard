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
 * Real-time notification subscription via WebSocket.
 *
 * Subscribes to notifications:{userId} topic and pushes incoming
 * notifications into the Pinia store. Re-fetches from DB on
 * tab visibility change for cross-tab consistency.
 *
 * Accepts a *getter* (not a snapshot) so the subscription can
 * re-target when ``authStore.user.id`` hydrates after the host
 * component (NotificationBell) has already mounted. The host uses
 * ``v-show`` rather than ``v-if`` to keep the bell mounted across
 * the rail collapse — that means setup runs once at the very first
 * render, and the userId at that moment may be empty. Without the
 * getter + watcher, the subscription would be wedged on
 * ``notifications:`` forever and WS pushes would never reach the
 * store; only ``fetchAll`` on tab refresh / visibility change
 * would populate the bell. This was the "toast only shows after
 * refresh" bug.
 */
import { onMounted, onUnmounted, watch } from 'vue'
import { subscribe, unsubscribe } from '@/services/socket'
import { onSocketReconnect } from '@/services/wsReconnect'
import { useNotificationStore } from '@/stores/notifications'
import type { AppNotification } from '@/types'

export function useNotificationSocket(getUserId: () => string) {
  const store = useNotificationStore()

  const handler = (data: unknown) => {
    store.addFromSocket(data as AppNotification)
  }

  // Track the currently-subscribed topic so we can unsubscribe cleanly
  // when the userId changes (e.g. team switch, or — the common case —
  // initial render with an empty userId followed by hydration).
  let currentTopic: string | null = null

  const syncSubscription = (userId: string): void => {
    const next = userId ? `notifications:${userId}` : null
    if (next === currentTopic) return
    if (currentTopic) {
      unsubscribe(currentTopic, handler)
    }
    currentTopic = next
    if (currentTopic) {
      subscribe(currentTopic, handler)
      // Pull any notifications missed before the subscription was
      // active — common on the very first userId hydration since
      // WS arrivals between mount and hydration go to the bogus
      // topic and are lost.
      void store.fetchAll()
    }
  }

  watch(getUserId, syncSubscription, { immediate: true })

  // Refetch on every WS reconnect — notifications fired during the
  // dropped-socket window aren't replayed, so the list would silently
  // miss entries until the next visibility change.
  const unregisterReconnect = onSocketReconnect(() => store.fetchAll())

  const onVisibility = () => {
    if (document.visibilityState === 'visible') {
      store.fetchAll()
    }
  }

  onMounted(() => {
    document.addEventListener('visibilitychange', onVisibility)
  })

  onUnmounted(() => {
    if (currentTopic) {
      unsubscribe(currentTopic, handler)
      currentTopic = null
    }
    unregisterReconnect()
    document.removeEventListener('visibilitychange', onVisibility)
  })
}
