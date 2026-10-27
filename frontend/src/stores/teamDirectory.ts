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
 * The active employee directory behind the profile's Team card: who shares
 * someone's manager and who reports to them. Read once per viewer and kept,
 * so moving between profiles and tabs doesn't fetch it again; a saved
 * employee record drops it (managers or status may have changed).
 *
 * The API serves the directory to employees:view only; callers check that
 * first rather than meeting a 403.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

import api from '@/services/api'
import type { DirectoryEntry } from '@/types/employee'
import { extractApiError } from '@/utils/errors'

export const useTeamDirectoryStore = defineStore('teamDirectory', () => {
  const rows = ref<DirectoryEntry[]>([])
  const error = ref('')
  // Whose view the rows are, so another sign-in in this tab never sees them.
  let loadedFor: string | null = null
  let inFlight: Promise<void> | null = null

  async function fetch(viewerId: string): Promise<void> {
    error.value = ''
    try {
      const { data } = await api.get<DirectoryEntry[]>('/v1/employees', {
        params: { status: 'active' },
      })
      rows.value = data
      loadedFor = viewerId
    } catch (err) {
      rows.value = []
      error.value = extractApiError(err, "Couldn't load the rest of the team.")
    } finally {
      inFlight = null
    }
  }

  /** Load for this viewer unless already loaded (or loading). */
  function ensureLoaded(viewerId: string): Promise<void> {
    if (loadedFor === viewerId && !error.value) return Promise.resolve()
    if (loadedFor !== viewerId) rows.value = []
    inFlight ??= fetch(viewerId)
    return inFlight
  }

  /** Forget the rows; the next ensureLoaded reads them again. */
  function invalidate(): void {
    loadedFor = null
  }

  return { rows, error, ensureLoaded, invalidate }
})
