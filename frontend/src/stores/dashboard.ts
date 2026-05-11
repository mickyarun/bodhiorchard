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
