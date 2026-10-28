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

import { computed, ref, watch } from 'vue'
import { useBugAttachments } from '@/composables/useBugAttachments'
import { acceptAttribute, attachmentRejectionReason } from '@/utils/attachments'
import {
  type AttachmentTileRow,
  attachmentHint,
  stagedTiles,
  storedTiles,
} from '@/utils/attachmentTiles'

/** Where the strip's files live: a stored bug, or files staged by the parent. */
export interface AttachmentStripSource {
  bugId: () => string | null
  staged: () => File[]
  setStaged: (files: File[]) => void
}

/**
 * State and actions behind BugAttachments.vue, in either of two modes:
 *
 * - **stored** (`bugId` set) — reads and writes through the API.
 * - **staged** (`bugId` null) — holds picked files with the parent until
 *   it has a bug to attach them to. The create dialog needs this because
 *   attachments are keyed on a bug that doesn't exist until the user hits
 *   "Report Bug".
 *
 * Both modes render the same strip, so a reporter sees no difference
 * between attaching before and after the bug is filed.
 */
export function useAttachmentStrip(source: AttachmentStripSource) {
  const attachments = useBugAttachments()
  const { items, limits, loading, uploading } = attachments
  const localError = ref<string | null>(null)

  const isStaging = computed(() => !source.bugId())

  // Both modes read the org's real limits: stored mode gets them with
  // the list, staging mode fetches them on mount (there is no bug to
  // list). `limits` starts at the shipped defaults, so the picker is
  // usable during that first round-trip.
  const effectiveLimits = computed(() => limits.value)

  const count = computed(() => (isStaging.value ? source.staged().length : items.value.length))
  const isFull = computed(() => count.value >= effectiveLimits.value.maxFilesPerBug)
  const accept = computed(() => acceptAttribute(effectiveLimits.value))
  const hint = computed(() => attachmentHint(effectiveLimits.value))

  // One message slot, fed by whichever layer failed — a client-side
  // rejection, a failed request, or a tile that couldn't fetch its blob.
  const message = computed({
    get: () => localError.value ?? attachments.error.value,
    set: (value: string | null) => {
      localError.value = value
      if (value === null) attachments.clearError()
    },
  })

  const tiles = computed<AttachmentTileRow[]>(() =>
    isStaging.value
      ? stagedTiles(source.staged())
      : storedTiles(items.value, id => attachments.downloadPath(source.bugId() as string, id)),
  )

  async function addFiles(picked: File[]): Promise<void> {
    if (isStaging.value) stageFiles(picked)
    else await attachments.uploadMany(source.bugId() as string, picked)
  }

  function stageFiles(picked: File[]): void {
    const next = [...source.staged()]
    for (const file of picked) {
      const reason = attachmentRejectionReason(file, effectiveLimits.value, next.length)
      if (reason) {
        message.value = reason
        break
      }
      next.push(file)
    }
    source.setStaged(next)
  }

  function removeTile(tile: AttachmentTileRow): void {
    message.value = null
    if (isStaging.value) {
      source.setStaged(source.staged().filter((f) => f !== tile.file))
      return
    }
    void attachments.remove(source.bugId() as string, tile.key)
  }

  /**
   * Upload the staged files to a bug that now exists.
   *
   * Called by the create dialog once `createBug` returns an id. Files
   * that land are dropped from the staged list; any that fail stay put
   * and visible, with the reason in the message slot, so the reporter
   * can retry them instead of losing them on close.
   *
   * @returns True when every staged file was stored.
   */
  async function flush(bugId: string): Promise<boolean> {
    if (!source.staged().length) return true
    const stored = await attachments.uploadMany(bugId, source.staged())
    // uploadMany stops at the first failure, so the successes are always
    // the leading slice of what was staged.
    const remaining = source.staged().slice(stored.length)
    source.setStaged(remaining)
    return remaining.length === 0
  }

  // Reload whenever the panel switches to a different bug, and clear any
  // message left over from the previous one.
  watch(
    source.bugId,
    (bugId) => {
      localError.value = null
      attachments.clearError()
      // A bug's list response carries the limits; without one, fetch
      // them on their own so the staged picker validates against the
      // org's real caps rather than the shipped defaults.
      if (bugId) void attachments.load(bugId)
      else void attachments.loadLimits()
    },
    { immediate: true },
  )

  return {
    loading, uploading, effectiveLimits, count, isFull, accept, hint, message, tiles,
    addFiles, removeTile, flush,
  }
}
