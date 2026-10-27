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
 * The active employee directory for the profile's Team card: who shares
 * someone's manager and who reports to them. Only callers with
 * employees:view may read it; without it the card shows the managers only.
 */
import { ref } from 'vue'

import api from '@/services/api'
import type { DirectoryEntry } from '@/types/employee'
import { extractApiError } from '@/utils/errors'

export function useTeamDirectory() {
  const rows = ref<DirectoryEntry[]>([])
  const error = ref('')
  let loaded = false
  let call = 0

  /** Read the directory once per card; later calls reuse it. */
  async function ensureLoaded(): Promise<void> {
    if (loaded) return
    const current = ++call
    error.value = ''
    try {
      const { data } = await api.get<DirectoryEntry[]>('/v1/employees', {
        params: { status: 'active' },
      })
      if (current !== call) return
      rows.value = data
      loaded = true
    } catch (err) {
      if (current === call) error.value = extractApiError(err, "Couldn't load the rest of the team.")
    }
  }

  function clear(): void {
    call += 1
    loaded = false
    rows.value = []
    error.value = ''
  }

  return { rows, error, ensureLoaded, clear }
}
