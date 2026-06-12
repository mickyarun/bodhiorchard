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
 * Mini-games store — daily play state + streak, score submission.
 *
 * First play of each game per UTC day awards XP (backend dedup);
 * any play keeps the platform-wide daily streak alive.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'

export interface MinigameInfo {
  key: string
  name: string
  played_today: boolean
  max_xp: number
}

export interface MinigameScoreResult {
  game: string
  xp_awarded: number
  first_play_today: boolean
  total_xp: number | null
  level: number | null
  level_changed: boolean
  streak_count: number
}

interface MinigameStatus {
  games: MinigameInfo[]
  streak_count: number
  streak_best: number
}

export const useMinigamesStore = defineStore('minigames', () => {
  const games = ref<MinigameInfo[]>([])
  const streakCount = ref(0)
  const streakBest = ref(0)
  const loading = ref(false)
  const error = ref('')

  async function fetchStatus(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.get<MinigameStatus>('/v1/minigames/status')
      games.value = data.games
      streakCount.value = data.streak_count
      streakBest.value = data.streak_best
    } catch {
      error.value = 'Failed to load mini-games'
    } finally {
      loading.value = false
    }
  }

  async function submitScore(game: string, score: number): Promise<MinigameScoreResult | null> {
    try {
      const { data } = await api.post<MinigameScoreResult>('/v1/minigames/score', {
        game,
        score,
      })
      streakCount.value = data.streak_count
      const entry = games.value.find((g) => g.key === game)
      if (entry) entry.played_today = true
      return data
    } catch {
      error.value = 'Failed to submit score'
      return null
    }
  }

  return { games, streakCount, streakBest, loading, error, fetchStatus, submitScore }
})
