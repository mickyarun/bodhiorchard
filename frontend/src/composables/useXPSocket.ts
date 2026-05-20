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
  type: 'xp_awarded' | 'sp_awarded' | 'level_up' | 'streak_milestone'
  xpAmount: number
  source: string
  levelName?: string
  level?: number
  streakCount?: number
}

// Labels for the "Recent XP Activity" feed. The xp_stage_* sources are the
// stage-promotion awards emitted when a tracked-repo PR merges into a
// configured develop / uat / main branch — see backend `stage_award.py`.
// `commit`, `pr_opened`, `pr_merged` no longer produce new awards, but keep
// the labels around so historical rows in a user's feed still render with
// the right copy.
const SOURCE_LABELS: Record<string, string> = {
  xp_stage_develop: 'Merged to develop',
  xp_stage_uat: 'Merged to UAT',
  xp_stage_prod: 'Merged to production',
  review: 'Code Review',
  bud_completed: 'BUD Completed',
  bud_contributor: 'BUD Contributor',
  streak: 'Daily Streak',
  quality_bonus: 'Quality Bonus',
  commit: 'Commit',
  pr_opened: 'PR Opened',
  pr_merged: 'PR Merged',
}

const SOURCE_ICONS: Record<string, string> = {
  xp_stage_develop: 'mdi-source-branch',
  xp_stage_uat: 'mdi-shield-check-outline',
  xp_stage_prod: 'mdi-rocket-launch-outline',
  review: 'mdi-eye-check-outline',
  bud_completed: 'mdi-leaf',
  bud_contributor: 'mdi-account-multiple',
  streak: 'mdi-fire',
  quality_bonus: 'mdi-star',
  commit: 'mdi-source-commit',
  pr_opened: 'mdi-source-pull',
  pr_merged: 'mdi-source-merge',
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
    const rewardType = raw.type as 'xp' | 'sp' | undefined
    const amount = (raw.amount as number) || 0
    const source = (raw.source as string) || ''

    // Both award_xp and award_sp publish to xp:{userId} — discriminate on
    // `type`. SP payloads carry skill_points but no level/streak/total, so
    // we must NOT overwrite those fields with defaults on an SP event.
    if (rewardType === 'sp') {
      xpStore.applyXPUpdate({
        amount,
        skill_points: raw.skill_points as number | undefined,
      })
    } else {
      xpStore.applyXPUpdate({
        amount,
        new_total: (raw.new_total as number) || 0,
        level: (raw.level as number) || 1,
        level_name: (raw.level_name as string) || 'seedling',
        streak_count: (raw.streak_count as number) || 0,
      })
    }

    // Toast: distinguish SP from XP so the user sees the right currency label.
    let toastType: XPToastItem['type']
    if (eventType === 'level_up') {
      toastType = 'level_up'
    } else if (rewardType === 'sp') {
      toastType = 'sp_awarded'
    } else {
      toastType = 'xp_awarded'
    }

    const toast: XPToastItem = {
      id: ++toastIdCounter,
      type: toastType,
      xpAmount: amount,
      source,
      levelName: (raw.level_name as string) || undefined,
      level: (raw.level as number) || undefined,
      streakCount: (raw.streak_count as number) || undefined,
    }
    toasts.value.push(toast)

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
