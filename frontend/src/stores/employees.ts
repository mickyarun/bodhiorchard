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
 * Employee directory and records (people workspace).
 *
 * Actions return `null` on success or a user-facing error string, so
 * views can show the server's own reason (e.g. "That would create a
 * reporting loop") next to the field that caused it.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

import api from '@/services/api'
import type {
  DirectoryEntry,
  EmployeeContact,
  EmployeeLeavePolicy,
  EmployeePersonal,
  EmployeeRecord,
  EmployeeStatus,
  EmployeeWork,
  ManagerInput,
  MemberCandidate,
} from '@/types/employee'
import { extractApiError } from '@/utils/errors'

export interface DirectoryFilters {
  q?: string
  department?: string
  status?: EmployeeStatus | null
}

/** `'me'` addresses the caller's own record. */
export type RecordKey = string | 'me'

export const useEmployeesStore = defineStore('employees', () => {
  const directory = ref<DirectoryEntry[]>([])
  const candidates = ref<MemberCandidate[]>([])
  const record = ref<EmployeeRecord | null>(null)
  const loading = ref(false)
  const error = ref('')
  /** HTTP status of the last failed record load (404 = no record yet). */
  const errorStatus = ref<number | null>(null)
  const candidatesState = ref<'idle' | 'loading' | 'loaded' | 'error'>('idle')
  // Latest record request; an older response that lands late is ignored
  // so quick navigation between profiles never shows the wrong person.
  let recordRequest = 0
  // Same for directory searches: a slow "a" must not overwrite "an".
  let directoryRequest = 0

  async function fetchDirectory(filters: DirectoryFilters = {}): Promise<void> {
    const current = ++directoryRequest
    loading.value = true
    error.value = ''
    try {
      const params = {
        q: filters.q || undefined,
        department: filters.department || undefined,
        status: filters.status || undefined,
      }
      const { data } = await api.get<DirectoryEntry[]>('/v1/employees', { params })
      if (current === directoryRequest) directory.value = data
    } catch (err) {
      if (current === directoryRequest) {
        error.value = extractApiError(err, "Couldn't load the employee directory.")
      }
    } finally {
      if (current === directoryRequest) loading.value = false
    }
  }

  async function fetchCandidates(): Promise<void> {
    candidatesState.value = 'loading'
    try {
      const { data } = await api.get<MemberCandidate[]>('/v1/employees/candidates')
      candidates.value = data
      candidatesState.value = 'loaded'
    } catch {
      candidates.value = []
      candidatesState.value = 'error'
    }
  }

  /** Load a record; a 404 on `'me'` means HR hasn't created one yet. */
  async function fetchRecord(key: RecordKey): Promise<void> {
    const request = ++recordRequest
    loading.value = true
    error.value = ''
    errorStatus.value = null
    record.value = null
    try {
      const { data } = await api.get<EmployeeRecord>(`/v1/employees/${key}`)
      if (request === recordRequest) record.value = data
    } catch (err) {
      if (request !== recordRequest) return
      error.value = extractApiError(err, "Couldn't load this employee record.")
      errorStatus.value = (err as { response?: { status?: number } }).response?.status ?? null
    } finally {
      if (request === recordRequest) loading.value = false
    }
  }

  async function save(request: () => Promise<{ data: EmployeeRecord }>, fallback: string) {
    try {
      record.value = (await request()).data
      return null
    } catch (err) {
      return extractApiError(err, fallback)
    }
  }

  async function createEmployee(userId: string, work: EmployeeWork): Promise<string | null> {
    return save(
      () => api.post<EmployeeRecord>('/v1/employees', { user_id: userId, work }),
      "Couldn't create the employee record.",
    )
  }

  async function updateWork(userId: string, work: EmployeeWork): Promise<string | null> {
    return save(
      () => api.put<EmployeeRecord>(`/v1/employees/${userId}/work`, work),
      "Couldn't save the work details.",
    )
  }

  async function updatePersonal(userId: string, personal: EmployeePersonal): Promise<string | null> {
    return save(
      () => api.put<EmployeeRecord>(`/v1/employees/${userId}/personal`, personal),
      "Couldn't save the personal details.",
    )
  }

  async function updateMyContact(contact: EmployeeContact): Promise<string | null> {
    return save(
      () => api.patch<EmployeeRecord>('/v1/employees/me', contact),
      "Couldn't save your details.",
    )
  }

  async function updateManagers(userId: string, managers: ManagerInput[]): Promise<string | null> {
    return save(
      () => api.put<EmployeeRecord>(`/v1/employees/${userId}/managers`, { managers }),
      "Couldn't save the reporting managers.",
    )
  }

  /** Show a leave policy change on the open record without reloading it. */
  function setLeavePolicy(userId: string, policy: EmployeeLeavePolicy): void {
    if (record.value?.user_id === userId) record.value = { ...record.value, leave_policy: policy }
  }

  return {
    directory,
    candidates,
    record,
    loading,
    error,
    errorStatus,
    candidatesState,
    fetchDirectory,
    fetchCandidates,
    fetchRecord,
    createEmployee,
    updateWork,
    updatePersonal,
    updateMyContact,
    updateManagers,
    setLeavePolicy,
  }
})
