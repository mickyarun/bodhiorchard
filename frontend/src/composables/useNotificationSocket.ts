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
 */
import { onMounted, onUnmounted } from 'vue'
import { subscribe, unsubscribe } from '@/services/socket'
import { onSocketReconnect } from '@/services/wsReconnect'
import { useNotificationStore } from '@/stores/notifications'
import type { AppNotification } from '@/types'

export function useNotificationSocket(userId: string) {
  const store = useNotificationStore()
  const topic = `notifications:${userId}`

  const handler = (data: unknown) => {
    store.addFromSocket(data as AppNotification)
  }

  subscribe(topic, handler)
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
    unsubscribe(topic, handler)
    unregisterReconnect()
    document.removeEventListener('visibilitychange', onVisibility)
  })
}
