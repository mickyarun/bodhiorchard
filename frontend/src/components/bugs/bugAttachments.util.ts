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

/** Tile rows and the limits hint for BugAttachments.vue. */
import type { BugAttachment, BugAttachmentLimits } from '@/types'

/** One tile in the attachment strip, staged (``file``) or stored (``fetchPath``). */
export interface AttachmentTileRow {
  key: string
  filename: string
  mimeType: string
  sizeBytes: number
  fetchPath: string | null
  file: File | null
}

/** Tiles for files picked before the bug exists. */
export function stagedTiles(files: File[]): AttachmentTileRow[] {
  return files.map((file, index) => ({
    key: `${index}-${file.name}-${file.lastModified}`,
    filename: file.name,
    mimeType: file.type,
    sizeBytes: file.size,
    fetchPath: null,
    file,
  }))
}

/** Tiles for a bug's stored attachments; ``pathFor`` gives each one's download path. */
export function storedTiles(
  items: BugAttachment[],
  pathFor: (attachmentId: string) => string,
): AttachmentTileRow[] {
  return items.map((a) => ({
    key: a.id,
    filename: a.filename,
    mimeType: a.mimeType,
    sizeBytes: a.sizeBytes,
    fetchPath: pathFor(a.id),
    file: null,
  }))
}

/** "Up to 5 files, 10 MB each (png, jpg, pdf)." */
export function attachmentHint(limits: BugAttachmentLimits): string {
  return (
    `Up to ${limits.maxFilesPerBug} files, ${limits.maxFileMb} MB each ` +
    `(${limits.acceptedExtensions.join(', ')}).`
  )
}
