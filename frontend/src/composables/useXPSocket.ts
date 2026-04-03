/**
 * useXPSocket — real-time XP notifications via WebSocket.
 *
 * Subscribes to `xp:{userId}` topic and updates the XP store
 * optimistically. Exposes a reactive toast queue for UI consumption.
 */
import { onMounted, onUnmounted, ref } from 'vue'
import { subscribe, unsubscribe } from '@/services/socket'
import { useXPStore } from '@/stores/xp'
import { useAuthStore } from '@/stores/auth'

// ─── Toast Types ───────────────────────────────

export interface XPToastItem {
  id: number
  type: 'xp_awarded' | 'level_up' | 'streak_milestone'
  xpAmount: number
  source: string
  levelName?: string
  level?: number
  streakCount?: number
}

const SOURCE_LABELS: Record<string, string> = {
  commit: 'Commit',
  pr_opened: 'PR Opened',
  pr_merged: 'PR Merged',
  review: 'Code Review',
  bud_completed: 'BUD Completed',
  streak: 'Daily Streak',
  quality_bonus: 'Quality Bonus',
}

const SOURCE_ICONS: Record<string, string> = {
  commit: 'mdi-source-commit',
  pr_opened: 'mdi-source-pull',
  pr_merged: 'mdi-source-merge',
  review: 'mdi-eye-check-outline',
  bud_completed: 'mdi-leaf',
  streak: 'mdi-fire',
  quality_bonus: 'mdi-star',
}

export function getSourceLabel(source: string): string {
  return SOURCE_LABELS[source] || source
}

export function getSourceIcon(source: string): string {
  return SOURCE_ICONS[source] || 'mdi-plus-circle'
}

// ─── Composable ────────────────────────────────

let toastIdCounter = 0

export function useXPSocket() {
  const xpStore = useXPStore()
  const authStore = useAuthStore()
  const toasts = ref<XPToastItem[]>([])
  let topic: string | null = null

  function dismissToast(id: number): void {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }

  function onXPEvent(data: unknown): void {
    const raw = data as Record<string, unknown>
    const eventType = raw.event_type as string
    const xpAmount = (raw.xp_amount as number) || 0
    const source = (raw.source as string) || ''

    // Update store optimistically
    xpStore.applyXPUpdate({
      xp_amount: xpAmount,
      new_total: (raw.new_total as number) || 0,
      level: (raw.level as number) || 1,
      level_name: (raw.level_name as string) || 'seedling',
      streak_count: (raw.streak_count as number) || 0,
    })

    // Push toast for UI
    const toast: XPToastItem = {
      id: ++toastIdCounter,
      type: eventType === 'level_up' ? 'level_up' : 'xp_awarded',
      xpAmount,
      source,
      levelName: (raw.level_name as string) || undefined,
      level: (raw.level as number) || undefined,
      streakCount: (raw.streak_count as number) || undefined,
    }
    toasts.value.push(toast)

    // Auto-dismiss after timeout
    const timeout = eventType === 'level_up' ? 5000 : 3000
    setTimeout(() => dismissToast(toast.id), timeout)
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

  return { toasts, dismissToast }
}
