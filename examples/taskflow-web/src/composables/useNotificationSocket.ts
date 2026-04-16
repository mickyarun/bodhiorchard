import { onUnmounted, toValue, type MaybeRefOrGetter } from 'vue'
import { useNotificationStore } from '@/stores/notifications'
import type { Notification } from '@/types/notification'

/**
 * Resolve the WebSocket base URL from Vite env. Prefers `VITE_WS_URL` (full
 * base, e.g. `wss://api.example.com`). Returns an empty string when no URL
 * is configured so the composable can skip connecting instead of hitting a
 * hardcoded localhost port.
 */
function buildWsBaseUrl(): string {
  const explicit = import.meta.env.VITE_WS_URL
  if (typeof explicit === 'string' && explicit.length > 0) {
    return explicit.replace(/\/$/, '')
  }
  return ''
}

type UserIdInput = MaybeRefOrGetter<string | number | null | undefined>

export function useNotificationSocket(userId: UserIdInput) {
  const store = useNotificationStore()
  let ws: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  const MAX_RETRIES = 5
  let retries = 0

  function connect() {
    const uid = toValue(userId)
    if (uid == null || uid === '') return
    const baseUrl = buildWsBaseUrl()
    if (!baseUrl) return
    const url = `${baseUrl}/ws/notifications?userId=${encodeURIComponent(String(uid))}`
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

    ws.onerror = () => {
      // `onclose` fires next and owns the reconnect/backoff logic; we only
      // need this handler so browsers don't log an "uncaught" warning.
    }

    ws.onclose = () => {
      if (retries < MAX_RETRIES) {
        const delay = Math.min(1000 * 2 ** retries, 30000)
        reconnectTimer = setTimeout(() => {
          retries++
          connect()
        }, delay)
      } else {
        store.setError('Real-time updates unavailable. Refresh to reconnect.')
      }
    }
  }

  function disconnect() {
    if (reconnectTimer) clearTimeout(reconnectTimer)
    if (ws) {
      ws.onclose = null
      ws.onerror = null
      ws.close()
      ws = null
    }
  }

  connect()
  onUnmounted(disconnect)

  return { disconnect }
}
