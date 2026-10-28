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

import { ref } from 'vue'
import api from '@/services/api'
import type { SlackAvatarSyncResult } from '@/types/celebrations'
import { photoImportSummary } from '@/utils/avatar'
import { extractApiError } from '@/utils/errors'

export interface PhotoImportOutcome {
  variant: 'success' | 'info' | 'error'
  text: string
}

/**
 * "Import photos from Slack": copies each linked member's Slack photo onto
 * anyone without one. A photo uploaded here is never replaced. Offered on
 * the employee directory (HR), Settings → Slack and Settings → Celebrations
 * (admins); the server allows HR and admins alike.
 */
export function useSlackPhotoImport() {
  const importing = ref(false)
  const outcome = ref<PhotoImportOutcome | null>(null)

  async function run(): Promise<boolean> {
    importing.value = true
    outcome.value = null
    try {
      const { data } = await api.post<SlackAvatarSyncResult>('/v1/employees/avatars/sync-slack', {
        overwrite: false,
      })
      outcome.value = { variant: data.updated ? 'success' : 'info', text: photoImportSummary(data) }
      return data.updated > 0
    } catch (err) {
      outcome.value = { variant: 'error', text: extractApiError(err, 'Failed to import photos from Slack') }
      return false
    } finally {
      importing.value = false
    }
  }

  return { importing, outcome, run }
}
