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
 * useMinigameRoom — shared lifecycle for a server-authoritative mini-game.
 *
 * Wraps a `MinigameRoomClient`: pulls auth from the store, creates the room on
 * mount, exposes the authoritative `score`/`round`/`status`, forwards
 * game-specific render events, fires `onResult` once with the recorded outcome,
 * and tears the connection down on unmount. Each game component supplies its own
 * event-rendering and result handler; everything else is identical.
 */
import { onMounted, onUnmounted, ref, type Ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import {
  MinigameRoomClient,
  type MinigameResult,
} from '@/multiplayer/MinigameRoomClient'

export type MinigameStatus = 'connecting' | 'playing' | 'finished' | 'error'

export interface MinigameRoomHandle {
  status: Ref<MinigameStatus>
  score: Ref<number>
  round: Ref<number>
  send: (type: string, payload?: unknown) => void
}

export function useMinigameRoom(
  game: string,
  handlers: {
    onEvent: (type: string, payload: unknown) => void
    onResult: (result: MinigameResult) => void
  },
): MinigameRoomHandle {
  const authStore = useAuthStore()
  const client = new MinigameRoomClient()
  const status = ref<MinigameStatus>('connecting')
  const score = ref(0)
  const round = ref(0)

  client.onState = (s) => {
    score.value = s.score
    round.value = s.round
    if (s.phase === 'finished') status.value = 'finished'
    else if (status.value === 'connecting') status.value = 'playing'
  }
  client.onEvent = handlers.onEvent
  client.onResult = handlers.onResult

  onMounted(async () => {
    const user = authStore.user
    if (!user) {
      status.value = 'error'
      return
    }
    try {
      await client.start(game, {
        userId: user.id,
        name: user.name,
        orgId: user.org_id,
        token: authStore.token ?? '',
      })
      if (status.value === 'connecting') status.value = 'playing'
    } catch (err) {
      console.error('[minigame] failed to start room:', err)
      status.value = 'error'
    }
  })

  onUnmounted(() => client.destroy())

  return {
    status,
    score,
    round,
    send: (type, payload) => client.send(type, payload),
  }
}
