/**
 * useXPSocket — real-time XP notifications via WebSocket.
 *
 * Subscribes to `xp:{userId}` topic and updates the XP store
 * optimistically on each award event. Shows a toast on level-up.
 */
import { onMounted, onUnmounted } from 'vue'
import { subscribe, unsubscribe } from '@/services/socket'
import { useXPStore } from '@/stores/xp'
import { useAuthStore } from '@/stores/auth'

export function useXPSocket() {
  const xpStore = useXPStore()
  const authStore = useAuthStore()
  let topic: string | null = null

  function onXPEvent(data: unknown): void {
    const raw = data as Record<string, unknown>
    const eventType = raw.event_type as string

    // Update store optimistically
    xpStore.applyXPUpdate({
      xp_amount: (raw.xp_amount as number) || 0,
      new_total: (raw.new_total as number) || 0,
      level: (raw.level as number) || 1,
      level_name: (raw.level_name as string) || 'seedling',
      streak_count: (raw.streak_count as number) || 0,
    })

    // Level-up notification (callers can listen for this via the store)
    if (eventType === 'level_up') {
      console.info(
        `[XP] Level up! Now level ${raw.level} (${raw.level_name})`,
      )
    }
  }

  onMounted(() => {
    const userId = authStore.user?.id
    if (!userId) return
    topic = `xp:${userId}`
    subscribe(topic, onXPEvent)
  })

  onUnmounted(() => {
    if (topic) {
      unsubscribe(topic, onXPEvent)
      topic = null
    }
  })
}
