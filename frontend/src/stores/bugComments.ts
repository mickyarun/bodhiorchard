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

/** The bug comment thread: state and calls, kept by the bugs store. */
import { type Ref, ref } from 'vue'
import api from '@/services/api'
import type { BugComment, BugCommentListResponse } from '@/types'
import { extractApiError } from '@/utils/errors'

/**
 * Comment state and calls for the bugs store. Failures land in the store's
 * shared ``error``; ``onCountChange`` keeps the cached comment counts on
 * the bug list, board and open bug in step with adds and deletes.
 */
export function createBugComments(
  error: Ref<string | null>,
  onCountChange: (bugId: string, delta: number) => void,
) {
  const comments = ref<BugComment[]>([])
  const commentsLoading = ref(false)

  // Tracks the bugId of the active comment fetch so a slow request
  // doesn't overwrite the thread after the user has navigated to a
  // different bug (or closed the drawer).
  let commentsRequestId = 0

  async function fetchComments(bugId: string): Promise<void> {
    commentsRequestId += 1
    const requestId = commentsRequestId
    commentsLoading.value = true
    error.value = null
    try {
      const { data } = await api.get<BugCommentListResponse>(`/v1/bugs/${bugId}/comments`)
      if (requestId === commentsRequestId) {
        comments.value = data.items
      }
    } catch (err) {
      if (requestId === commentsRequestId) {
        error.value = extractApiError(err, 'Failed to load comments.')
      }
    } finally {
      if (requestId === commentsRequestId) {
        commentsLoading.value = false
      }
    }
  }

  async function addComment(bugId: string, body: string): Promise<BugComment | null> {
    error.value = null
    try {
      const { data } = await api.post<BugComment>(`/v1/bugs/${bugId}/comments`, { body })
      comments.value.push(data)
      onCountChange(bugId, 1)
      return data
    } catch (err) {
      error.value = extractApiError(err, 'Failed to post comment.')
      return null
    }
  }

  async function editComment(
    bugId: string,
    commentId: string,
    body: string,
  ): Promise<BugComment | null> {
    error.value = null
    try {
      const { data } = await api.patch<BugComment>(
        `/v1/bugs/${bugId}/comments/${commentId}`,
        { body },
      )
      const idx = comments.value.findIndex((c) => c.id === commentId)
      if (idx >= 0) comments.value[idx] = data
      return data
    } catch (err) {
      error.value = extractApiError(err, 'Failed to edit comment.')
      return null
    }
  }

  async function deleteComment(bugId: string, commentId: string): Promise<boolean> {
    error.value = null
    try {
      const { data } = await api.delete<BugComment>(
        `/v1/bugs/${bugId}/comments/${commentId}`,
      )
      const idx = comments.value.findIndex((c) => c.id === commentId)
      if (idx >= 0) comments.value[idx] = data
      onCountChange(bugId, -1)
      return true
    } catch (err) {
      error.value = extractApiError(err, 'Failed to delete comment.')
      return false
    }
  }

  return { comments, commentsLoading, fetchComments, addComment, editComment, deleteComment }
}
