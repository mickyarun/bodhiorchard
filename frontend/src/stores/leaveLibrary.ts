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
 * The org's leave type library (leave:configure), and linking a policy's
 * types to it. Policy-side actions reload that policy's types afterwards.
 * Actions return `null` or a user-facing error string.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

import api from '@/services/api'
import type { LibraryTypeAdd, LibraryTypeRead, LibraryTypeWrite, LinkedTypeWrite } from '@/types/leaveLibrary'
import type { LeaveTypeRead } from '@/types/leavePolicy'
import { useLeavePolicyConfigStore } from '@/stores/leavePolicyConfig'
import { extractApiError } from '@/utils/errors'

export const useLeaveLibraryStore = defineStore('leaveLibrary', () => {
  const entries = ref<LibraryTypeRead[]>([])
  const error = ref('')
  const loading = ref(false)

  async function fetchEntries(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.get<LibraryTypeRead[]>('/v1/leave/library-types')
      entries.value = data
    } catch (err) {
      error.value = extractApiError(err, "Couldn't load the leave type library. Reload to try again.")
    } finally {
      loading.value = false
    }
  }

  /** Adds or edits a library type; an edit applies to every policy using it. */
  async function saveEntry(body: LibraryTypeWrite, id: string | null): Promise<string | null> {
    try {
      if (id) await api.put<LibraryTypeRead>(`/v1/leave/library-types/${id}`, body)
      else await api.post<LibraryTypeRead>('/v1/leave/library-types', body)
    } catch (err) {
      return extractApiError(err, "Couldn't save the library type. Check the fields and try again.")
    }
    await fetchEntries()
    return null
  }

  /** Deletes a library type no policy uses (the server refuses otherwise). */
  async function deleteEntry(id: string): Promise<string | null> {
    try {
      await api.delete(`/v1/leave/library-types/${id}`)
    } catch (err) {
      return extractApiError(err, "Couldn't delete the library type. Try again.")
    }
    await fetchEntries()
    return null
  }

  /** Adds a library type to a policy. */
  function addToPolicy(policyId: string, body: LibraryTypeAdd): Promise<string | null> {
    return policyWrite(policyId, () => api.post(`/v1/leave/policies/${policyId}/library-types`, body))
  }

  /** Makes a policy's own type follow a library type. */
  function linkExisting(type: LeaveTypeRead, body: LibraryTypeAdd): Promise<string | null> {
    return policyWrite(type.policy_id, () => api.post(`/v1/leave/types/${type.id}/link`, body))
  }

  /** Sets a linked type's quota on its policy, or switches it off there. */
  function updateLink(type: LeaveTypeRead, body: LinkedTypeWrite): Promise<string | null> {
    return policyWrite(type.policy_id, () => api.put(`/v1/leave/types/${type.id}/link`, body))
  }

  /** The policy keeps the type as its own, with its current rules. */
  function unlink(type: LeaveTypeRead): Promise<string | null> {
    return policyWrite(type.policy_id, () => api.delete(`/v1/leave/types/${type.id}/link`))
  }

  async function policyWrite(policyId: string, write: () => Promise<unknown>): Promise<string | null> {
    try {
      await write()
    } catch (err) {
      return extractApiError(err, "Couldn't update the leave type. Try again.")
    }
    await useLeavePolicyConfigStore().fetchTypes(policyId)
    // Which policies use each library type just changed.
    if (entries.value.length) void fetchEntries()
    return null
  }

  return {
    entries,
    error,
    loading,
    fetchEntries,
    saveEntry,
    deleteEntry,
    addToPolicy,
    linkExisting,
    updateLink,
    unlink,
  }
})
