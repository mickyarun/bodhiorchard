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
 * XP Store — developer experience points, level, streak, and unlocks.
 *
 * Fetches from /api/v1/xp/* endpoints. Provides reactive XP profile
 * data for the character selection UI and level badge rendering.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { XPProfile, LeaderboardEntry, RewardEvent } from '@/types'
import api from '@/services/api'

export const useXPStore = defineStore('xp', () => {
  const profile = ref<XPProfile | null>(null)
  const leaderboard = ref<LeaderboardEntry[]>([])
  const history = ref<RewardEvent[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchProfile(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get<XPProfile>('/v1/xp/me')
      profile.value = data
    } catch (err) {
      error.value = 'Failed to load XP profile'
      console.error('[XPStore] fetchProfile failed:', err)
    } finally {
      loading.value = false
    }
  }

  async function fetchLeaderboard(): Promise<void> {
    try {
      const { data } = await api.get<LeaderboardEntry[]>('/v1/xp/leaderboard')
      leaderboard.value = data
    } catch (err) {
      console.error('[XPStore] fetchLeaderboard failed:', err)
    }
  }

  async function fetchHistory(): Promise<void> {
    try {
      const { data } = await api.get<RewardEvent[]>('/v1/xp/history')
      history.value = data
    } catch (err) {
      console.error('[XPStore] fetchHistory failed:', err)
    }
  }

  /** Update profile optimistically from a WebSocket reward event.
   *
   * XP events set new_total/level/level_name/streak_count. SP events only
   * carry skill_points — the XP fields are left untouched so an SP award
   * doesn't visually reset the user's level/streak display.
   */
  function applyXPUpdate(update: {
    amount: number
    new_total?: number
    level?: number
    level_name?: string
    streak_count?: number
    skill_points?: number
  }): void {
    if (!profile.value) return
    if (update.new_total !== undefined) profile.value.total_xp = update.new_total
    if (update.level !== undefined) profile.value.level = update.level
    if (update.level_name !== undefined) profile.value.level_name = update.level_name
    if (update.streak_count !== undefined) profile.value.streak_count = update.streak_count
    if (update.skill_points !== undefined) profile.value.skill_points = update.skill_points
  }

  return {
    profile,
    leaderboard,
    history,
    loading,
    error,
    fetchProfile,
    fetchLeaderboard,
    fetchHistory,
    applyXPUpdate,
  }
})
