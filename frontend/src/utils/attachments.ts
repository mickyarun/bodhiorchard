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
 * Pure helpers for the bug-attachment picker.
 *
 * Client-side checks here are a courtesy, not a control: they turn a
 * doomed 10 MB upload into an instant inline message. The backend
 * re-validates everything against the org's policy
 * (`app/services/upload_policy.py`), which is the real gate.
 *
 * Kept free of Vue and of network calls so both the live panel and the
 * staged picker in the create dialog can share them, and so they are
 * directly unit-testable.
 */

import type { BugAttachmentLimits } from '@/types'

/**
 * Fallback limits used before the server's real ones arrive (and in the
 * create dialog, which has no bug to fetch them for yet). Mirrors the
 * backend's `BugAttachmentSettings` defaults; an org with different
 * limits simply gets a slightly stale hint until the list loads, and
 * the server still has the final say.
 */
export const DEFAULT_ATTACHMENT_LIMITS: BugAttachmentLimits = {
  maxFileMb: 10,
  maxFilesPerBug: 10,
  acceptedExtensions: ['.jpeg', '.jpg', '.pdf', '.png', '.xls', '.xlsx'],
}

/** Value for an `<input type="file">` `accept` attribute, e.g. `.jpg,.pdf`. */
export function acceptAttribute(limits: BugAttachmentLimits): string {
  return limits.acceptedExtensions.join(',')
}

/** Human-readable size: `856 KB`, `2.4 MB`. */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** Lowercased extension including the dot, or `''` when there is none. */
export function fileExtension(filename: string): string {
  const dot = filename.lastIndexOf('.')
  // A dot at position 0 is a leading-dot name (".gitignore"), not an
  // extension, and a trailing dot leaves an empty one — both are
  // rejected by returning '' rather than a bogus match.
  if (dot <= 0 || dot === filename.length - 1) return ''
  return filename.slice(dot).toLowerCase()
}

/**
 * Why `file` can't be attached, or `null` if it can.
 *
 * @param file - The file the user picked.
 * @param limits - The org's limits, from the attachment list response.
 * @param currentCount - Attachments already on (or staged for) this bug.
 */
export function attachmentRejectionReason(
  file: File,
  limits: BugAttachmentLimits,
  currentCount: number,
): string | null {
  if (currentCount >= limits.maxFilesPerBug) {
    return `Limit of ${limits.maxFilesPerBug} files reached. Remove one before adding another.`
  }
  const ext = fileExtension(file.name)
  if (!limits.acceptedExtensions.includes(ext)) {
    return `"${file.name}" isn't a supported type. Allowed: ${limits.acceptedExtensions.join(', ')}.`
  }
  if (file.size > limits.maxFileMb * 1024 * 1024) {
    return `"${file.name}" is ${formatFileSize(file.size)} — the limit is ${limits.maxFileMb} MB.`
  }
  if (file.size === 0) {
    return `"${file.name}" is empty.`
  }
  return null
}

/** True when the attachment should render as a thumbnail rather than an icon. */
export function isPreviewableImage(mimeType: string): boolean {
  return mimeType.startsWith('image/')
}

/** MDI icon name for a non-image attachment. */
export function attachmentIcon(mimeType: string): string {
  if (mimeType === 'application/pdf') return 'mdi-file-pdf-box'
  if (mimeType.includes('spreadsheet') || mimeType.includes('ms-excel')) {
    return 'mdi-file-excel-box'
  }
  if (mimeType.startsWith('text/')) return 'mdi-file-document-outline'
  if (mimeType.startsWith('video/')) return 'mdi-file-video-outline'
  if (mimeType.startsWith('audio/')) return 'mdi-file-music-outline'
  return 'mdi-file-outline'
}
