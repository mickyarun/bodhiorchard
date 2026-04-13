/**
 * Standup Store — daily team activity reports.
 *
 * Fetches from /api/v1/standups/* endpoints. Provides reactive
 * standup data for the StandupPanel dashboard component.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { StandupReport, StandupReportListItem } from '@/types/standup'
import api from '@/services/api'

export const useStandupStore = defineStore('standup', () => {
  const report = ref<StandupReport | null>(null)
  const recentList = ref<StandupReportListItem[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchToday(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get<StandupReport>('/v1/standups/today')
      report.value = data
    } catch (err) {
      error.value = 'Failed to load standup'
      console.error('[StandupStore] fetchToday failed:', err)
    } finally {
      loading.value = false
    }
  }

  async function fetchByDate(date: string): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get<StandupReport>(`/v1/standups/${date}`)
      report.value = data
    } catch (err) {
      error.value = 'No standup found for this date'
      report.value = null
      console.error('[StandupStore] fetchByDate failed:', err)
    } finally {
      loading.value = false
    }
  }

  async function fetchRecent(): Promise<void> {
    try {
      const { data } = await api.get<StandupReportListItem[]>('/v1/standups/list')
      recentList.value = data
    } catch (err) {
      console.error('[StandupStore] fetchRecent failed:', err)
    }
  }

  return {
    report,
    recentList,
    loading,
    error,
    fetchToday,
    fetchByDate,
    fetchRecent,
  }
})
