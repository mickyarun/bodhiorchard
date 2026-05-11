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

import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'

export interface RaceLeaderboardRow {
  userId: string
  userName: string
  distanceM: number
  finishTimeMs: number | null
  finishedAt: string
}

interface RaceLeaderboardResponse {
  distanceM: number
  entries: RaceLeaderboardRow[]
}

/**
 * Per-distance race leaderboard cache. Two arrays — one per allowed distance
 * — so the Leaderboard view can switch tabs without re-fetching. The store
 * is deliberately thin; sorting + limiting happen server-side in
 * `app/repositories/race_result.py::leaderboard_by_distance`.
 */
export const useRaceLeaderboardStore = defineStore('raceLeaderboard', () => {
  const entries100 = ref<RaceLeaderboardRow[]>([])
  const entries200 = ref<RaceLeaderboardRow[]>([])
  const loading100 = ref(false)
  const loading200 = ref(false)
  const error = ref<string>('')

  async function fetchLeaderboard(distance: 100 | 200, limit = 50): Promise<void> {
    const loadingRef = distance === 100 ? loading100 : loading200
    const targetRef = distance === 100 ? entries100 : entries200
    loadingRef.value = true
    error.value = ''
    try {
      const { data } = await api.get<RaceLeaderboardResponse>(
        '/v1/races/leaderboard',
        { params: { distance, limit } },
      )
      targetRef.value = data.entries
    } catch (err) {
      console.error('[raceLeaderboard] fetch failed:', err)
      error.value = 'Failed to load race leaderboard'
    } finally {
      loadingRef.value = false
    }
  }

  return { entries100, entries200, loading100, loading200, error, fetchLeaderboard }
})
