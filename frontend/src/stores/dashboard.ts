// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'
import type { TreeData } from '@/types/dashboard'

export const useDashboardStore = defineStore('dashboard', () => {
  const treeData = ref<TreeData | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchTreeData(refresh = false): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const params: Record<string, string> = {}
      if (refresh) params.refresh = 'true'
      const { data } = await api.get('/v1/dashboard/tree-data', { params, timeout: 120000 })
      treeData.value = data
    } catch {
      error.value = 'Failed to load tree data.'
    } finally {
      loading.value = false
    }
  }

  return {
    treeData,
    loading,
    error,
    fetchTreeData,
  }
})
