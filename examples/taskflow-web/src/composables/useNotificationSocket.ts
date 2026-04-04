import { onUnmounted } from 'vue'
import { useNotificationStore } from '@/stores/notifications'
import type { Notification } from '@/types/notification'

export function useNotificationSocket(userId: string | number) {
  const store = useNotificationStore()
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  const MAX_RETRIES = 5
  let retries = 0

  function connect() {
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${protocol}://${location.hostname}:9001/ws/notifications?userId=${userId}`
    ws = new WebSocket(url)

    ws.onmessage = (event) => {
      try {
        const notification: Notification = JSON.parse(event.data)
        store.addItem(notification)
      } catch {
        // Ignore malformed messages
      }
    }

    ws.onopen = () => {
      retries = 0
    }

    ws.onclose = () => {
      if (retries < MAX_RETRIES) {
        const delay = Math.min(1000 * 2 ** retries, 30000)
        reconnectTimer = setTimeout(() => {
          retries++
          connect()
        }, delay)
      }
    }
  }

  function disconnect() {
    if (reconnectTimer) clearTimeout(reconnectTimer)
    if (ws) {
      ws.onclose = null
      ws.close()
      ws = null
    }
  }

  connect()
  onUnmounted(disconnect)

  return { disconnect }
}
