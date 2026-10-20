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
 * Leave reports: summary, requests (register) and balances, with filters
 * and CSV export. HR and the owner (leave:reports) see everyone; a manager
 * sees their direct reports. `noAccess` is set when the API says neither.
 */
import { isAxiosError } from 'axios'
import { defineStore } from 'pinia'
import { reactive, ref } from 'vue'

import api from '@/services/api'
import type {
  BalanceReport,
  RegisterReport,
  ReportFilters,
  ReportName,
  ReportScope,
  SummaryReport,
} from '@/types/leaveReports'
import { filenameFrom, saveBlob } from '@/utils/download'
import { extractApiError, extractBlobApiError } from '@/utils/errors'
import { presetRange, type RangePreset } from '@/utils/leaveRanges'

const PEOPLE = ['user_id', 'department', 'office_id', 'policy_id', 'manager_id'] as const
/** The filters each report takes; the rest stay out of its query string. */
export const REPORT_FILTERS: Record<ReportName, readonly (keyof ReportFilters)[]> = {
  summary: ['start', 'end', ...PEOPLE],
  register: ['start', 'end', ...PEOPLE, 'kind', 'leave_type_id', 'status'],
  balances: ['year', ...PEOPLE],
}

export function reportParams(name: ReportName, filters: ReportFilters): Record<string, string | number> {
  const out: Record<string, string | number> = {}
  for (const key of REPORT_FILTERS[name]) {
    const value = filters[key]
    if (value !== null && value !== '') out[key] = value
  }
  return out
}

/** Filter values the new scope doesn't offer (e.g. another viewer's picks). */
export function outOfScope(filters: ReportFilters, scope: ReportScope): (keyof ReportFilters)[] {
  const people = new Set(scope.people.map(p => p.user_id))
  const offered: Partial<Record<keyof ReportFilters, Set<string>>> = {
    user_id: people,
    manager_id: people,
    department: new Set(scope.departments),
    office_id: new Set(scope.offices.map(o => o.id)),
    policy_id: new Set(scope.policies.map(p => p.id)),
    leave_type_id: new Set(scope.leave_types.map(t => t.id)),
  }
  return (Object.keys(offered) as (keyof ReportFilters)[]).filter(key => {
    const value = filters[key]
    return typeof value === 'string' && value !== '' && !offered[key]?.has(value)
  })
}

export const useLeaveReportsStore = defineStore('leaveReports', () => {
  const report = ref<ReportName>('summary')
  const preset = ref<RangePreset>('this_month')
  const filters = reactive<ReportFilters>({
    ...presetRange('this_month', new Date()),
    year: null,
    user_id: null,
    department: null,
    office_id: null,
    policy_id: null,
    manager_id: null,
    kind: null,
    leave_type_id: null,
    status: null,
  })
  const scope = ref<ReportScope | null>(null)
  const noAccess = ref(false)
  const summary = ref<SummaryReport | null>(null)
  const register = ref<RegisterReport | null>(null)
  const balances = ref<BalanceReport | null>(null)
  const loading = ref(false)
  const exporting = ref(false)
  const error = ref('')
  /** Kept apart from `error`, which each report fetch clears. */
  const scopeError = ref('')
  let call = 0

  /** Who the viewer can report on. The store outlives a sign-out, so this
   *  also drops the previous viewer's reports and filter picks. */
  async function loadScope(): Promise<void> {
    summary.value = register.value = balances.value = null
    scopeError.value = ''
    try {
      const loaded = (await api.get<ReportScope>('/v1/leave/reports/scope')).data
      for (const key of outOfScope(filters, loaded)) Object.assign(filters, { [key]: null })
      scope.value = loaded
      noAccess.value = false
    } catch (err) {
      scope.value = null
      noAccess.value = isAxiosError(err) && err.response?.status === 403
      if (!noAccess.value) scopeError.value = extractApiError(err, "Couldn't load the filter choices.")
    }
  }

  function setPreset(next: RangePreset): void {
    preset.value = next
    Object.assign(filters, presetRange(next, new Date(), { start: filters.start, end: filters.end }))
  }

  async function fetch(): Promise<void> {
    const current = ++call
    const name = report.value
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.get(`/v1/leave/reports/${name}`, {
        params: reportParams(name, filters),
      })
      if (current !== call) return
      if (name === 'summary') summary.value = data as SummaryReport
      else if (name === 'register') register.value = data as RegisterReport
      else balances.value = data as BalanceReport
    } catch (err) {
      if (current === call) error.value = extractApiError(err, "Couldn't load this report.")
    } finally {
      if (current === call) loading.value = false
    }
  }

  /** Download the current report as CSV; returns an error message or null. */
  async function exportCsv(): Promise<string | null> {
    const name = report.value
    exporting.value = true
    try {
      const response = await api.get<Blob>(`/v1/leave/reports/${name}.csv`, {
        params: reportParams(name, filters),
        responseType: 'blob',
      })
      const disposition = response.headers['content-disposition'] as string | undefined
      saveBlob(response.data, filenameFrom(disposition, `leave-${name}.csv`))
      return null
    } catch (err) {
      return await extractBlobApiError(err, "Couldn't export this report.")
    } finally {
      exporting.value = false
    }
  }

  return {
    report, preset, filters, scope, noAccess, summary, register, balances,
    loading, exporting, error, scopeError, loadScope, setPreset, fetch, exportCsv,
  }
})
