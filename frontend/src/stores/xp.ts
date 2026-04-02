/**
 * XP Store — developer experience points, level, streak, and unlocks.
 *
 * Fetches from /api/v1/xp/* endpoints. Provides reactive XP profile
 * data for the character selection UI and level badge rendering.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { XPProfile, LeaderboardEntry, XPEvent } from '@/types'
import api from '@/services/api'

export const useXPStore = defineStore('xp', () => {
  const profile = ref<XPProfile | null>(null)
  const leaderboard = ref<LeaderboardEntry[]>([])
  const history = ref<XPEvent[]>([])
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
      const { data } = await api.get<XPEvent[]>('/v1/xp/history')
      history.value = data
    } catch (err) {
      console.error('[XPStore] fetchHistory failed:', err)
    }
  }

  /** Update profile optimistically from a WebSocket XP event. */
  function applyXPUpdate(update: {
    xp_amount: number
    new_total: number
    level: number
    level_name: string
    streak_count: number
  }): void {
    if (!profile.value) return
    profile.value.total_xp = update.new_total
    profile.value.level = update.level
    profile.value.level_name = update.level_name
    profile.value.streak_count = update.streak_count
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
