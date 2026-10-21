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
 * Leave approvals queue for managers and HR. Approve / reject return
 * `null` on success or the server's reason (e.g. 409: already decided).
 */
import { isAxiosError } from 'axios'
import { defineStore } from 'pinia'
import { reactive, ref } from 'vue'

import api from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import { useLeaveStore } from '@/stores/leave'
import type { ApprovalItem, ApprovalPage, LeaveKind, LeaveRequestRead, LeaveTypeBrief, PersonRef } from '@/types/leave'
import { extractApiError } from '@/utils/errors'
import { rangeProblem } from '@/utils/leaveRanges'

/** New dates for approved leave, and an optional note for the requester. */
export interface RescheduleInput {
  start_date: string
  end_date: string
  half_day: string
  note?: string | null
}

export type ApprovalTab = 'pending' | 'decided'

/** Optional narrowing; empty strings / null don't filter. */
export interface ApprovalFilters {
  start: string
  end: string
  kind: LeaveKind | null
  leave_type_id: string | null
  user_id: string | null
}

export function approvalParams(status: ApprovalTab, filters: ApprovalFilters): Record<string, string> {
  const params: Record<string, string> = { status }
  for (const [key, value] of Object.entries(filters)) {
    if (value) params[key] = value as string
  }
  return params
}

export const useLeaveApprovalsStore = defineStore('leaveApprovals', () => {
  const items = ref<ApprovalItem[]>([])
  /** Only the newest decisions came back; dates or filters reach the rest. */
  const truncated = ref(false)
  const status = ref<ApprovalTab>('pending')
  const loading = ref(false)
  const error = ref('')
  /** Why a card vanished: someone else decided it first. Cleared on a tab switch or the next decision. */
  const notice = ref('')
  const filters = reactive<ApprovalFilters>({ start: '', end: '', kind: null, leave_type_id: null, user_id: null })
  /** Pickers' options, from the unfiltered queue so they don't shrink as you filter. */
  const people = ref<PersonRef[]>([])
  const leaveTypes = ref<LeaveTypeBrief[]>([])
  let call = 0
  /** Whose queue the filters and pickers belong to; the store outlives a sign-out. */
  let viewer: string | null = null

  /** Drop filters and picker names left by whoever used this tab before. */
  function forgetPreviousViewer(): void {
    const current = useAuthStore().user?.id ?? null
    if (current === viewer) return
    viewer = current
    Object.assign(filters, { start: '', end: '', kind: null, leave_type_id: null, user_id: null })
    people.value = []
    leaveTypes.value = []
  }

  async function fetch(next: ApprovalTab = status.value): Promise<void> {
    const current = ++call
    forgetPreviousViewer()
    if (next !== status.value) notice.value = ''
    status.value = next
    error.value = rangeProblem(filters, false) ?? ''
    if (error.value) {
      loading.value = false
      return
    }
    loading.value = true
    try {
      const { data } = await api.get<ApprovalPage>('/v1/leave/approvals', {
        params: approvalParams(next, filters),
      })
      if (current !== call) return
      items.value = data.items
      truncated.value = data.truncated
      if (!filters.user_id && !filters.leave_type_id) remember(data.items)
    } catch (err) {
      if (current === call) {
        error.value = extractApiError(err, "Couldn't load approvals. Reload to try again.")
      }
    } finally {
      if (current === call) loading.value = false
    }
  }

  async function decide(
    id: string,
    action: 'approve' | 'reject',
    note: string | null,
  ): Promise<string | null> {
    try {
      await api.post<LeaveRequestRead>(`/v1/leave/requests/${id}/${action}`, { note })
    } catch (err) {
      const message = extractApiError(err, `Couldn't ${action} this request. Reload and try again.`)
      // 409: another approver decided first, or the request was cancelled.
      // The refresh drops the card, so say why at the top of the queue.
      if (isAxiosError(err) && err.response?.status === 409) {
        notice.value = message
        void refresh()
      }
      return message
    }
    // A decided request leaves the pending queue.
    notice.value = ''
    items.value = items.value.filter(item => item.request.id !== id)
    void useLeaveStore().fetchApprovalCount()
    return null
  }

  /** Change approved leave; the card shows the request as it now stands. */
  async function change(
    id: string,
    action: 'withdraw' | 'reschedule',
    body: Record<string, string | null>,
  ): Promise<string | null> {
    try {
      const { data } = await api.post<LeaveRequestRead>(`/v1/leave/requests/${id}/${action}`, body)
      items.value = items.value.map(item => (item.request.id === id ? { ...item, request: data } : item))
      return null
    } catch (err) {
      return extractApiError(err, "Couldn't change this leave. Reload and try again.")
    }
  }

  function withdraw(id: string, note: string): Promise<string | null> {
    return change(id, 'withdraw', { note: note.trim() })
  }

  function reschedule(id: string, dates: RescheduleInput): Promise<string | null> {
    return change(id, 'reschedule', { ...dates, note: dates.note?.trim() || null })
  }

  function remember(data: ApprovalItem[]): void {
    const byId = new Map(people.value.map(p => [p.user_id, p]))
    const types = new Map(leaveTypes.value.map(t => [t.id, t]))
    for (const { request } of data) {
      byId.set(request.user.user_id, request.user)
      if (request.leave_type) types.set(request.leave_type.id, request.leave_type)
    }
    people.value = [...byId.values()].sort((a, b) => a.name.localeCompare(b.name))
    leaveTypes.value = [...types.values()].sort((a, b) => a.name.localeCompare(b.name))
  }

  function refresh(): void {
    void fetch()
    void useLeaveStore().fetchApprovalCount()
  }

  function approve(id: string, note: string): Promise<string | null> {
    return decide(id, 'approve', note.trim() || null)
  }

  function reject(id: string, note: string): Promise<string | null> {
    return decide(id, 'reject', note.trim())
  }

  return {
    items, truncated, status, filters, people, leaveTypes, loading, error, notice,
    forgetPreviousViewer, fetch, approve, reject, withdraw, reschedule,
  }
})
