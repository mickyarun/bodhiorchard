// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/*
 * Pinia store backing the Features tab.
 *
 * Single fetch path: fetchPage() hits /v1/features with limit/offset.
 * Top contributors load lazily per-repo and memoise in contributorsByRepo
 * so re-rendering doesn't refetch.
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'
import type { Feature, FeaturePage, RepoContributor } from '@/types'

export const PAGE_SIZE = 24

interface FetchPageArgs {
  page?: number
  repoId?: string
  q?: string
}

export const useFeaturesStore = defineStore('features', () => {
  const items = ref<Feature[]>([])
  const total = ref(0)
  const selectedFeature = ref<Feature | null>(null)
  const contributorsByRepo = ref<Record<string, RepoContributor[]>>({})
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchPage({ page = 1, repoId, q }: FetchPageArgs = {}): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const params: Record<string, string | number> = {
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      }
      if (repoId) params.repoId = repoId
      if (q) params.q = q
      const { data } = await api.get<FeaturePage>('/v1/features', { params })
      items.value = data.items
      total.value = data.total
    } catch {
      error.value = 'Failed to load features.'
      items.value = []
      total.value = 0
    } finally {
      loading.value = false
    }
  }

  async function fetchFeature(id: string): Promise<void> {
    error.value = null
    try {
      const { data } = await api.get<Feature>(`/v1/features/${id}`)
      selectedFeature.value = data
    } catch {
      error.value = 'Failed to load feature.'
    }
  }

  async function fetchTopContributors(repoId: string): Promise<void> {
    if (contributorsByRepo.value[repoId]) return
    try {
      const { data } = await api.get<RepoContributor[]>('/v1/features/contributors', {
        params: { repoId },
      })
      contributorsByRepo.value = { ...contributorsByRepo.value, [repoId]: data }
    } catch {
      contributorsByRepo.value = { ...contributorsByRepo.value, [repoId]: [] }
    }
  }

  function reset(): void {
    items.value = []
    total.value = 0
    selectedFeature.value = null
    contributorsByRepo.value = {}
    error.value = null
  }

  return {
    items,
    total,
    selectedFeature,
    contributorsByRepo,
    loading,
    error,
    fetchPage,
    fetchFeature,
    fetchTopContributors,
    reset,
  }
})
