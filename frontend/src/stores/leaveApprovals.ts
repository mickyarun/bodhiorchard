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
import { useLeaveStore } from '@/stores/leave'
import type { ApprovalItem, LeaveKind, LeaveRequestRead, LeaveTypeBrief, PersonRef } from '@/types/leave'
import { extractApiError } from '@/utils/errors'

export type ApprovalTab = 'pending' | 'decided'

/** Optional narrowing; empty strings / null don't filter. */
export interface ApprovalFilters {
  start: string
  end: string
  kind: LeaveKind | null
  leave_type_id: string | null
  user_id: string | null
}

/** Only the newest decisions come back; past this, narrow the dates. */
export const DECIDED_LIMIT = 200

export function approvalParams(status: ApprovalTab, filters: ApprovalFilters): Record<string, string> {
  const params: Record<string, string> = { status }
  for (const [key, value] of Object.entries(filters)) {
    if (value) params[key] = value as string
  }
  return params
}

export const useLeaveApprovalsStore = defineStore('leaveApprovals', () => {
  const items = ref<ApprovalItem[]>([])
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

  async function fetch(next: ApprovalTab = status.value): Promise<void> {
    const current = ++call
    if (next !== status.value) notice.value = ''
    status.value = next
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.get<ApprovalItem[]>('/v1/leave/approvals', {
        params: approvalParams(next, filters),
      })
      if (current !== call) return
      items.value = data
      if (!filters.user_id && !filters.leave_type_id) remember(data)
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

  return { items, status, filters, people, leaveTypes, loading, error, notice, fetch, approve, reject }
})
