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
 * One policy's leave types and holiday calendar (leave:configure).
 * Actions return `null` or a user-facing error string.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

import api from '@/services/api'
import type {
  HolidayAdminRead,
  HolidayImportResult,
  HolidayWrite,
  LeaveTypeRead,
  LeaveTypeWrite,
} from '@/types/leavePolicy'
import { extractApiError } from '@/utils/errors'

export const useLeavePolicyConfigStore = defineStore('leavePolicyConfig', () => {
  const types = ref<LeaveTypeRead[]>([])
  const typesError = ref('')
  const holidays = ref<HolidayAdminRead[]>([])
  const holidaysError = ref('')
  const loading = ref(false)
  // Latest request per list: a slow answer for another policy or year that
  // lands late is dropped, so the list always matches what's selected.
  let typesRequest = 0
  let holidaysRequest = 0
  // The leave year the holiday list shows: a new or moved holiday may
  // belong to another one, so writes reload this year from the server.
  let holidaysYear: number | null = null

  async function fetchTypes(policyId: string): Promise<void> {
    const request = ++typesRequest
    typesError.value = ''
    try {
      const { data } = await api.get<LeaveTypeRead[]>(`/v1/leave/policies/${policyId}/types`)
      if (request === typesRequest) types.value = data
    } catch (err) {
      if (request !== typesRequest) return
      types.value = []
      typesError.value = extractApiError(err, "Couldn't load leave types. Reload to try again.")
    }
  }

  async function saveType(
    policyId: string,
    body: LeaveTypeWrite,
    typeId: string | null,
  ): Promise<string | null> {
    try {
      if (typeId) await api.put<LeaveTypeRead>(`/v1/leave/types/${typeId}`, body)
      else await api.post<LeaveTypeRead>(`/v1/leave/policies/${policyId}/types`, body)
    } catch (err) {
      return extractApiError(err, "Couldn't save the leave type. Check the fields and try again.")
    }
    await fetchTypes(policyId)
    return null
  }

  async function fetchHolidays(policyId: string, year: number): Promise<void> {
    const request = ++holidaysRequest
    holidaysYear = year
    loading.value = true
    holidaysError.value = ''
    try {
      const { data } = await api.get<HolidayAdminRead[]>(
        `/v1/leave/policies/${policyId}/holidays`,
        { params: { year } },
      )
      if (request === holidaysRequest) {
        holidays.value = [...data].sort((a, b) => a.date.localeCompare(b.date))
      }
    } catch (err) {
      if (request !== holidaysRequest) return
      holidays.value = []
      holidaysError.value = extractApiError(err, "Couldn't load holidays. Reload to try again.")
    } finally {
      if (request === holidaysRequest) loading.value = false
    }
  }

  async function addHoliday(policyId: string, body: HolidayWrite): Promise<string | null> {
    try {
      await api.post<HolidayAdminRead>(`/v1/leave/policies/${policyId}/holidays`, body)
      if (holidaysYear !== null) await fetchHolidays(policyId, holidaysYear)
      return null
    } catch (err) {
      return extractApiError(err, "Couldn't add the holiday. Check the date and try again.")
    }
  }

  async function updateHoliday(holiday: HolidayAdminRead, body: HolidayWrite): Promise<string | null> {
    try {
      const { data } = await api.put<HolidayAdminRead>(`/v1/leave/holidays/${holiday.id}`, body)
      holidays.value = holidays.value.map(h => (h.id === data.id ? data : h))
      return null
    } catch (err) {
      return extractApiError(err, "Couldn't update the holiday. Try again.")
    }
  }

  async function deleteHoliday(id: string): Promise<string | null> {
    try {
      await api.delete(`/v1/leave/holidays/${id}`)
      holidays.value = holidays.value.filter(h => h.id !== id)
      return null
    } catch (err) {
      return extractApiError(err, "Couldn't delete the holiday. Try again.")
    }
  }

  /** Returns how many were added, or an error string. */
  async function importHolidays(
    policyId: string,
    year: number,
  ): Promise<HolidayImportResult | string> {
    try {
      const { data } = await api.post<HolidayImportResult>(
        `/v1/leave/policies/${policyId}/holidays/import`,
        { year },
      )
      await fetchHolidays(policyId, year)
      return data
    } catch (err) {
      return extractApiError(
        err,
        "Couldn't import public holidays. Check the policy's country and try again.",
      )
    }
  }

  return {
    types,
    typesError,
    holidays,
    holidaysError,
    loading,
    fetchTypes,
    saveType,
    fetchHolidays,
    addHoliday,
    updateHoliday,
    deleteHoliday,
    importHolidays,
  }
})
