// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Real-time notification subscription via WebSocket.
 *
 * Subscribes to notifications:{userId} topic and pushes incoming
 * notifications into the Pinia store. Re-fetches from DB on
 * tab visibility change for cross-tab consistency.
 */
import { onMounted, onUnmounted } from 'vue'
import { subscribe, unsubscribe } from '@/services/socket'
import { useNotificationStore } from '@/stores/notifications'
import type { AppNotification } from '@/types'

export function useNotificationSocket(userId: string) {
  const store = useNotificationStore()
  const topic = `notifications:${userId}`

  const handler = (data: unknown) => {
    store.addFromSocket(data as AppNotification)
  }

  subscribe(topic, handler)

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
    document.removeEventListener('visibilitychange', onVisibility)
  })
}
