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
import type { LinkedFeature, LinkFeaturesResponse } from '@/types'
import api from '@/services/api'
import { extractApiError } from '@/utils/errors'

export const useBudLinkedFeaturesStore = defineStore('budLinkedFeatures', () => {
  const byBudId = ref<Record<string, LinkedFeature[]>>({})
  const loading = ref(false)
  const error = ref('')

  async function fetch(budId: string): Promise<LinkedFeature[] | null> {
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.get<LinkedFeature[]>(`/v1/buds/${budId}/linked-features`)
      byBudId.value = { ...byBudId.value, [budId]: data }
      return data
    } catch (err) {
      error.value = extractApiError(err, 'Failed to load linked features')
      return null
    } finally {
      loading.value = false
    }
  }

  async function link(
    budId: string,
    featureIds: string[],
  ): Promise<LinkFeaturesResponse | null> {
    error.value = ''
    try {
      const { data } = await api.post<LinkFeaturesResponse>(
        `/v1/buds/${budId}/linked-features`,
        { featureIds },
      )
      await fetch(budId)
      return data
    } catch (err) {
      error.value = extractApiError(err, 'Failed to link features')
      return null
    }
  }

  async function unlink(budId: string, featureId: string): Promise<boolean> {
    error.value = ''
    try {
      await api.delete(`/v1/buds/${budId}/linked-features/${featureId}`)
      await fetch(budId)
      return true
    } catch (err) {
      error.value = extractApiError(err, 'Failed to unlink feature')
      return false
    }
  }

  return { byBudId, loading, error, fetch, link, unlink }
})
