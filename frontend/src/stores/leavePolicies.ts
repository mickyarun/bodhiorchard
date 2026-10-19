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
 * Leave policies (leave:configure): the policy list, holiday countries,
 * and who follows each policy. Types and holidays live in
 * leavePolicyConfig.ts. Actions return `null` or a user-facing error.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

import api from '@/services/api'
import type { PersonRef } from '@/types/leave'
import type {
  AssignResult,
  HolidayCountry,
  PolicyRead,
  PolicyWrite,
} from '@/types/leavePolicy'
import { extractApiError } from '@/utils/errors'

export const useLeavePoliciesStore = defineStore('leavePolicies', () => {
  const policies = ref<PolicyRead[]>([])
  const countries = ref<HolidayCountry[]>([])
  const employees = ref<PersonRef[]>([])
  const loading = ref(false)
  const error = ref('')

  async function fetchPolicies(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      policies.value = (await api.get<PolicyRead[]>('/v1/leave/policies')).data
    } catch (err) {
      error.value = extractApiError(err, "Couldn't load leave policies. Reload to try again.")
    } finally {
      loading.value = false
    }
  }

  async function fetchCountries(): Promise<void> {
    if (countries.value.length) return
    try {
      countries.value = (await api.get<HolidayCountry[]>('/v1/leave/holiday-countries')).data
    } catch {
      // The country picker stays empty; a policy can still be saved without one.
      countries.value = []
    }
  }

  function replace(updated: PolicyRead): void {
    policies.value = policies.value.map(p => (p.id === updated.id ? updated : p))
  }

  /** Returns the new policy, or an error string. */
  async function createPolicy(body: PolicyWrite): Promise<PolicyRead | string> {
    try {
      const { data } = await api.post<PolicyRead>('/v1/leave/policies', body)
      policies.value = [...policies.value, data]
      return data
    } catch (err) {
      return extractApiError(err, "Couldn't create the policy. Check the fields and try again.")
    }
  }

  async function updatePolicy(id: string, body: PolicyWrite): Promise<string | null> {
    try {
      replace((await api.put<PolicyRead>(`/v1/leave/policies/${id}`, body)).data)
      return null
    } catch (err) {
      return extractApiError(err, "Couldn't save the policy. Check the fields and try again.")
    }
  }

  async function makeDefault(id: string): Promise<string | null> {
    try {
      await api.post<PolicyRead>(`/v1/leave/policies/${id}/default`)
    } catch (err) {
      return extractApiError(err, "Couldn't make this the default policy. Try again.")
    }
    await fetchPolicies()
    return null
  }

  async function deletePolicy(id: string): Promise<string | null> {
    try {
      await api.delete(`/v1/leave/policies/${id}`)
      policies.value = policies.value.filter(p => p.id !== id)
      return null
    } catch (err) {
      return extractApiError(err, "Couldn't delete the policy. Move its employees first.")
    }
  }

  async function fetchEmployees(policyId: string): Promise<string | null> {
    try {
      employees.value = (await api.get<PersonRef[]>(`/v1/leave/policies/${policyId}/employees`)).data
      return null
    } catch (err) {
      employees.value = []
      return extractApiError(err, "Couldn't load this policy's employees. Reload to try again.")
    }
  }

  /** Move people onto a policy; resolves to the result, or an error message. */
  async function assign(policyId: string, userIds: string[]): Promise<AssignResult | string> {
    let result: AssignResult
    try {
      result = (
        await api.post<AssignResult>(`/v1/leave/policies/${policyId}/assign`, {
          user_ids: userIds,
        })
      ).data
    } catch (err) {
      return extractApiError(err, "Couldn't move these employees. Try again.")
    }
    await Promise.all([fetchEmployees(policyId), fetchPolicies()])
    return result
  }

  return {
    policies,
    countries,
    employees,
    loading,
    error,
    fetchPolicies,
    fetchCountries,
    createPolicy,
    updatePolicy,
    makeDefault,
    deletePolicy,
    fetchEmployees,
    assign,
  }
})
