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
