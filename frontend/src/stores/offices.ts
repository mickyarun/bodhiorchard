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
 * The org's offices. Anyone can list them (the profile's office picker);
 * adding, changing and deleting need employees:manage. Actions return
 * `null` or a user-facing error.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

import api from '@/services/api'
import type { OfficeRead, OfficeWrite } from '@/types/office'
import { extractApiError } from '@/utils/errors'

export const useOfficesStore = defineStore('offices', () => {
  const offices = ref<OfficeRead[]>([])
  const loading = ref(false)
  const error = ref('')

  // Always refetched: policy names and head counts change under other HR
  // users, and a cached list would outlive a sign-out into another org.
  async function fetchOffices(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      offices.value = (await api.get<OfficeRead[]>('/v1/offices')).data
    } catch (err) {
      error.value = extractApiError(err, "Couldn't load offices. Reload to try again.")
    } finally {
      loading.value = false
    }
  }

  /** Create (no id) or update an office; the server returns the whole list. */
  async function saveOffice(body: OfficeWrite, id: string | null): Promise<string | null> {
    try {
      const response = id
        ? await api.put<OfficeRead[]>(`/v1/offices/${id}`, body)
        : await api.post<OfficeRead[]>('/v1/offices', body)
      offices.value = response.data
      return null
    } catch (err) {
      return extractApiError(err, "Couldn't save the office. Try again.")
    }
  }

  async function deleteOffice(id: string): Promise<string | null> {
    try {
      await api.delete(`/v1/offices/${id}`)
      offices.value = offices.value.filter(o => o.id !== id)
      return null
    } catch (err) {
      return extractApiError(err, "Couldn't delete the office. Try again.")
    }
  }

  return { offices, loading, error, fetchOffices, saveOffice, deleteOffice }
})
