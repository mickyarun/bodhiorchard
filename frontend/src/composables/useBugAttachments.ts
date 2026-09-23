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

import { ref } from 'vue'
import api from '@/services/api'
import { extractApiError } from '@/utils/errors'
import { DEFAULT_ATTACHMENT_LIMITS, attachmentRejectionReason } from '@/utils/attachments'
import type { BugAttachment, BugAttachmentLimits, BugAttachmentListResponse } from '@/types'

/**
 * CRUD over one bug's attachments.
 *
 * Lives outside the bugs store because attachments are scoped to the
 * single bug currently open, not to board-wide state — and because the
 * create dialog needs to upload a staged batch against a bug that does
 * not exist until `createBug` returns.
 *
 * The org's limits ride along with every list response, so the picker
 * knows the real caps without a separate settings fetch.
 */
export function useBugAttachments() {
  const items = ref<BugAttachment[]>([])
  const limits = ref<BugAttachmentLimits>({ ...DEFAULT_ATTACHMENT_LIMITS })
  const loading = ref(false)
  const uploading = ref(false)
  const error = ref<string | null>(null)

  // Which bug `items` currently describes. The create dialog stays
  // mounted for the life of the page and reuses this one instance for
  // every bug filed, so without an explicit target the previous bug's
  // uploads keep accumulating in `items` and count against the next
  // bug's per-bug cap — the second report of a session would be
  // rejected as "limit reached" with nothing attached to it.
  const targetBugId = ref<string | null>(null)

  /** Point the list at `bugId`, clearing it when the bug changes. */
  function retarget(bugId: string): void {
    if (targetBugId.value === bugId) return
    targetBugId.value = bugId
    items.value = []
  }

  /** Load a bug's attachments and the org's current limits. */
  async function load(bugId: string): Promise<void> {
    retarget(bugId)
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get<BugAttachmentListResponse>(
        `/v1/bugs/${bugId}/attachments`,
      )
      items.value = data.items
      limits.value = data.limits
    } catch (err) {
      error.value = extractApiError(err, 'Failed to load attachments.')
    } finally {
      loading.value = false
    }
  }

  /**
   * Load just the org's limits, for a bug that doesn't exist yet.
   *
   * The create dialog stages files before `createBug` runs, so it has
   * no list response to read limits from. Falling back to the shipped
   * defaults would wrongly reject a file that an org with a higher cap
   * allows, so fetch the real ones up front. A failure here is silent:
   * the defaults remain, and the server is the real gate either way.
   */
  async function loadLimits(): Promise<void> {
    try {
      const { data } = await api.get<BugAttachmentLimits>('/v1/bugs/attachments/limits')
      limits.value = data
    } catch {
      // Keep the defaults — this is a hint, not a control.
    }
  }

  /**
   * Upload one file and append it to the list on success.
   *
   * @returns The stored attachment, or `null` when the upload failed
   *   (in which case `error` carries the reason).
   */
  async function upload(bugId: string, file: File): Promise<BugAttachment | null> {
    retarget(bugId)
    const reason = attachmentRejectionReason(file, limits.value, items.value.length)
    if (reason) {
      error.value = reason
      return null
    }

    uploading.value = true
    error.value = null
    const form = new FormData()
    form.append('file', file)
    try {
      const { data } = await api.post<BugAttachment>(
        `/v1/bugs/${bugId}/attachments`,
        form,
      )
      items.value.push(data)
      return data
    } catch (err) {
      error.value = extractApiError(err, `Failed to upload "${file.name}".`)
      return null
    } finally {
      uploading.value = false
    }
  }

  /**
   * Upload several files in sequence, stopping at the first failure.
   *
   * Sequential rather than parallel on purpose: the per-bug cap is
   * enforced server-side with a count-then-insert, so a parallel burst
   * could slip past it, and a shared connection makes several large
   * uploads slower in parallel anyway. Stopping on the first failure
   * keeps the surfaced error the one that actually happened rather
   * than the last of several.
   *
   * @returns The attachments that were stored before any failure.
   */
  async function uploadMany(bugId: string, files: File[]): Promise<BugAttachment[]> {
    const stored: BugAttachment[] = []
    for (const file of files) {
      const saved = await upload(bugId, file)
      if (!saved) break
      stored.push(saved)
    }
    return stored
  }

  /** Delete an attachment, removing it from the list on success. */
  async function remove(bugId: string, attachmentId: string): Promise<boolean> {
    error.value = null
    try {
      await api.delete(`/v1/bugs/${bugId}/attachments/${attachmentId}`)
      items.value = items.value.filter((a) => a.id !== attachmentId)
      return true
    } catch (err) {
      error.value = extractApiError(err, 'Failed to delete the attachment.')
      return false
    }
  }

  /** Path of the authenticated download endpoint for one attachment. */
  function downloadPath(bugId: string, attachmentId: string): string {
    return `/v1/bugs/${bugId}/attachments/${attachmentId}`
  }

  function clearError(): void {
    error.value = null
  }

  return {
    items,
    limits,
    loading,
    uploading,
    error,
    load,
    loadLimits,
    upload,
    uploadMany,
    remove,
    downloadPath,
    clearError,
  }
}
