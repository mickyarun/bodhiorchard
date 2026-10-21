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
 * The caller's own leave: summary, requests, and the approvals badge.
 *
 * Actions return `null` on success or a user-facing error string, so the
 * page can show the server's reason (e.g. an overlapping request).
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

import api from '@/services/api'
import type {
  ApprovalCount,
  LeavePreview,
  LeaveRequestCreate,
  LeaveRequestRead,
  LeaveSummary,
  RequestScope,
} from '@/types/leave'
import { extractApiError } from '@/utils/errors'

export const useLeaveStore = defineStore('leave', () => {
  const summary = ref<LeaveSummary | null>(null)
  const summaryLoading = ref(false)
  const summaryError = ref('')
  const requests = ref<LeaveRequestRead[]>([])
  const requestsLoading = ref(false)
  const requestsError = ref('')
  const scope = ref<RequestScope>('upcoming')
  const approvalCount = ref<ApprovalCount>({ pending: 0, is_approver: false, has_reports: false })
  // Latest requests fetch; a slower, older scope never overwrites a newer one.
  let requestsCall = 0

  async function fetchSummary(): Promise<void> {
    summaryLoading.value = true
    summaryError.value = ''
    try {
      summary.value = (await api.get<LeaveSummary>('/v1/leave/me/summary')).data
    } catch (err) {
      summaryError.value = extractApiError(err, "Couldn't load your leave balances. Reload to try again.")
    } finally {
      summaryLoading.value = false
    }
  }

  async function fetchRequests(next: RequestScope = scope.value): Promise<void> {
    const call = ++requestsCall
    scope.value = next
    requestsLoading.value = true
    requestsError.value = ''
    try {
      const { data } = await api.get<LeaveRequestRead[]>('/v1/leave/me/requests', {
        params: { scope: next },
      })
      if (call === requestsCall) requests.value = data
    } catch (err) {
      if (call === requestsCall) {
        requestsError.value = extractApiError(err, "Couldn't load your requests. Reload to try again.")
      }
    } finally {
      if (call === requestsCall) requestsLoading.value = false
    }
  }

  async function preview(
    body: LeaveRequestCreate,
  ): Promise<{ data: LeavePreview | null; error: string }> {
    try {
      const { data } = await api.post<LeavePreview>('/v1/leave/requests/preview', body)
      return { data, error: '' }
    } catch (err) {
      return { data: null, error: extractApiError(err, "Couldn't check this request. Try again.") }
    }
  }

  /** Send a request, then refresh balances and the list. */
  async function createRequest(body: LeaveRequestCreate): Promise<string | null> {
    try {
      await api.post<LeaveRequestRead>('/v1/leave/requests', body)
    } catch (err) {
      return extractApiError(err, "Couldn't send your request. Try again.")
    }
    await Promise.all([fetchSummary(), fetchRequests()])
    return null
  }

  async function cancelRequest(id: string): Promise<string | null> {
    try {
      await api.post<LeaveRequestRead>(`/v1/leave/requests/${id}/cancel`)
    } catch (err) {
      return extractApiError(err, "Couldn't cancel this request. Reload and try again.")
    }
    await Promise.all([fetchSummary(), fetchRequests()])
    return null
  }

  /** The nav badge; failures leave the item hidden rather than erroring. */
  async function fetchApprovalCount(): Promise<void> {
    try {
      approvalCount.value = (await api.get<ApprovalCount>('/v1/leave/approvals/count')).data
    } catch {
      approvalCount.value = { pending: 0, is_approver: false, has_reports: false }
    }
  }

  return {
    summary,
    summaryLoading,
    summaryError,
    requests,
    requestsLoading,
    requestsError,
    scope,
    approvalCount,
    fetchSummary,
    fetchRequests,
    preview,
    createRequest,
    cancelRequest,
    fetchApprovalCount,
  }
})
