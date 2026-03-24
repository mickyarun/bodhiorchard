/**
 * Generic composable for subscribing to a real-time topic.
 *
 * Usage:
 *   const { data, connected } = useRealtimeChannel<ScanStatus>(`scan:${scanId}`)
 *   // data.value updates reactively on every push from the server
 */
import { ref, watch, onUnmounted, toValue, type Ref } from 'vue'
import { subscribe, unsubscribe, isConnected } from '@/services/socket'

export function useRealtimeChannel<T = unknown>(topic: string | Ref<string>) {
  const data = ref<T | null>(null) as Ref<T | null>
  const connected = ref(false)

  let activeTopic: string | null = null

  const callback = (payload: unknown) => {
    data.value = payload as T
    connected.value = isConnected()
  }

  function sub(t: string): void {
    if (activeTopic) {
      unsubscribe(activeTopic, callback)
    }
    activeTopic = t
    data.value = null
    subscribe(t, callback)
    connected.value = isConnected()
  }

  function unsub(): void {
    if (activeTopic) {
      unsubscribe(activeTopic, callback)
      activeTopic = null
    }
    connected.value = false
  }

  // Handle both static string and reactive Ref<string>
  if (typeof topic === 'string') {
    sub(topic)
  } else {
    sub(toValue(topic))
    watch(topic, (newTopic) => {
      if (newTopic) sub(newTopic)
      else unsub()
    })
  }

  onUnmounted(unsub)

  return { data, connected }
}
