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
 * Subscribes to the org quiz topic `quiz:{orgId}` and keeps the player store in
 * sync with live open/reveal events. Mirrors useXPSocket's subscribe/cleanup
 * pattern. The monthly SP toast needs no code here — award_sp already publishes
 * on `xp:{userId}`, which useXPSocket renders.
 */
import { onMounted, onUnmounted } from 'vue'

import { subscribe, unsubscribe } from '@/services/socket'
import { useAuthStore } from '@/stores/auth'
import { useQuizStore } from '@/stores/quiz'

export function useQuizSocket(): void {
  const authStore = useAuthStore()
  const quizStore = useQuizStore()
  let topic: string | null = null

  async function onQuizEvent(data: unknown): Promise<void> {
    const event = (data as Record<string, unknown>).event_type
    if (event === 'quiz_opened') {
      // Clear the prior quiz's reveal so the phase machine falls through to the
      // freshly-opened question instead of staying stuck on the old reveal.
      quizStore.reveal = null
      await quizStore.fetchActive()
    } else if (event === 'quiz_revealed') {
      const current = quizStore.active
      if (current) await quizStore.fetchReveal(current.id)
      await quizStore.fetchActive()
      await quizStore.fetchMonthly()
    }
  }

  onMounted(() => {
    const orgId = authStore.user?.org_id
    if (!orgId) return
    topic = `quiz:${orgId}`
    subscribe(topic, onQuizEvent)
  })

  onUnmounted(() => {
    if (topic) {
      unsubscribe(topic, onQuizEvent)
      topic = null
    }
  })
}
