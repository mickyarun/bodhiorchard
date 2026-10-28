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
import { extractApiError } from '@/utils/errors'

// Must stay in step with AVATAR_POLICY on the backend, which is the
// authority — this only saves the user an upload round-trip.
export const AVATAR_ACCEPT = 'image/png,image/jpeg,image/gif,image/webp'
const MAX_BYTES = 20 * 1024 * 1024

export interface AvatarEditorEvents {
  /** The new stored URL, or null after a removal. */
  updated: (avatarUrl: string | null) => void
  error: (message: string) => void
}

/**
 * Upload or remove one member's profile photo. The server decides who may
 * (the member themself, or HR); this only reports the outcome. Shared by
 * the profile photo's camera button and the account menu.
 */
export function useAvatarEditor(userId: () => string, on: AvatarEditorEvents) {
  const busy = ref(false)

  /** The `change` handler for an `<input type="file" :accept="AVATAR_ACCEPT">`. */
  async function onPick(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement
    const file = input.files?.[0]
    // Clear immediately so picking the same file twice still fires change.
    input.value = ''
    if (!file) return

    if (file.size > MAX_BYTES) {
      on.error('That photo is larger than 20 MB.')
      return
    }

    busy.value = true
    try {
      const body = new FormData()
      body.append('file', file)
      const { data } = await api.post<{ avatar_url: string | null }>(
        `/v1/employees/${userId()}/avatar`,
        body,
      )
      on.updated(data.avatar_url)
    } catch (err) {
      on.error(extractApiError(err, 'Failed to upload that photo'))
    } finally {
      busy.value = false
    }
  }

  async function remove(): Promise<void> {
    busy.value = true
    try {
      await api.delete(`/v1/employees/${userId()}/avatar`)
      on.updated(null)
    } catch (err) {
      on.error(extractApiError(err, 'Failed to remove that photo'))
    } finally {
      busy.value = false
    }
  }

  return { busy, onPick, remove }
}
