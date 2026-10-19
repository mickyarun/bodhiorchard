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
import { ref } from 'vue'

import api from '@/services/api'
import { useLeaveStore } from '@/stores/leave'
import type { ApprovalItem, LeaveRequestRead } from '@/types/leave'
import { extractApiError } from '@/utils/errors'

export type ApprovalTab = 'pending' | 'decided'

export const useLeaveApprovalsStore = defineStore('leaveApprovals', () => {
  const items = ref<ApprovalItem[]>([])
  const status = ref<ApprovalTab>('pending')
  const loading = ref(false)
  const error = ref('')
  let call = 0

  async function fetch(next: ApprovalTab = status.value): Promise<void> {
    const current = ++call
    status.value = next
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.get<ApprovalItem[]>('/v1/leave/approvals', {
        params: { status: next },
      })
      if (current === call) items.value = data
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
      if (isAxiosError(err) && err.response?.status === 409) void refresh()
      return message
    }
    // A decided request leaves the pending queue.
    items.value = items.value.filter(item => item.request.id !== id)
    void useLeaveStore().fetchApprovalCount()
    return null
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

  return { items, status, loading, error, fetch, approve, reject }
})
