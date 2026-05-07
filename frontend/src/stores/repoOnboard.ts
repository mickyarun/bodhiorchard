// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Pinia store fronting the Phase B/C bulk-onboard endpoints.
 *
 * Kept separate from ``useSettingsStore`` because that file already
 * carries the connections + tracked-repo surface area; this store has
 * no shared state with it and is only loaded on the bulk-import tab.
 */

import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'
import { extractApiError } from '@/utils/errors'
import type {
  BulkOnboardJobCreated,
  BulkOnboardRequestBody,
  InstallableListResponse,
  RepoBranchListResponse,
} from '@/types/repoOnboard'

export const useRepoOnboardStore = defineStore('repoOnboard', () => {
  const lastError = ref<string | null>(null)

  async function loadInstallableRepos(): Promise<InstallableListResponse | null> {
    try {
      const { data } = await api.get<InstallableListResponse>('/v1/settings/repos/installable')
      lastError.value = null
      return data
    } catch (err) {
      lastError.value = extractApiError(err, 'Failed to load installable repositories.')
      return null
    }
  }

  async function loadInstallableBranches(fullName: string): Promise<string[] | null> {
    const [owner, repo] = fullName.split('/')
    if (!owner || !repo) {
      lastError.value = `Invalid repository name: ${fullName}`
      return null
    }
    try {
      const { data } = await api.get<RepoBranchListResponse>(
        `/v1/settings/repos/installable/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}/branches`,
      )
      lastError.value = null
      return data.branches
    } catch (err) {
      lastError.value = extractApiError(err, `Failed to load branches for ${fullName}.`)
      return null
    }
  }

  async function submitBulkOnboard(
    body: BulkOnboardRequestBody,
  ): Promise<BulkOnboardJobCreated | null> {
    try {
      const { data } = await api.post<BulkOnboardJobCreated>(
        '/v1/settings/repos/bulk-onboard',
        body,
      )
      lastError.value = null
      return data
    } catch (err) {
      lastError.value = extractApiError(err, 'Failed to submit bulk onboard request.')
      return null
    }
  }

  return {
    lastError,
    loadInstallableRepos,
    loadInstallableBranches,
    submitBulkOnboard,
  }
})
