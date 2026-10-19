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

/** One person's masked details, saving changes, and revealing one value. */
import { ref } from 'vue'

import api from '@/services/api'
import type { SensitiveField, SensitiveRead, SensitiveWrite } from '@/types/employeeRecords'
import { extractApiError } from '@/utils/errors'

export function useSensitiveDetails(userId: () => string) {
  const data = ref<SensitiveRead | null>(null)
  const loading = ref(false)
  const error = ref('')

  async function load(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      data.value = (await api.get<SensitiveRead>(`/v1/employees/${userId()}/sensitive`)).data
    } catch (err) {
      error.value = extractApiError(err, "Couldn't load these details.")
    } finally {
      loading.value = false
    }
  }

  async function save(body: SensitiveWrite): Promise<string | null> {
    try {
      data.value = (await api.put<SensitiveRead>(`/v1/employees/${userId()}/sensitive`, body)).data
      return null
    } catch (err) {
      return extractApiError(err, "Couldn't save. Check the formats and try again.")
    }
  }

  /** The full value (null when not saved), or why it couldn't be shown. */
  async function reveal(field: SensitiveField): Promise<{ value: string | null } | { error: string }> {
    try {
      const response = await api.post<{ value: string | null }>(
        `/v1/employees/${userId()}/sensitive/reveal`,
        { field },
      )
      return { value: response.data.value }
    } catch (err) {
      return { error: extractApiError(err, "Couldn't show this value.") }
    }
  }

  return { data, loading, error, load, save, reveal }
}
