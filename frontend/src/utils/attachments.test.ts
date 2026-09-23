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

import { describe, expect, it } from 'vitest'
import {
  DEFAULT_ATTACHMENT_LIMITS,
  acceptAttribute,
  attachmentIcon,
  attachmentRejectionReason,
  fileExtension,
  formatFileSize,
} from './attachments'
import type { BugAttachmentLimits } from '@/types'

const LIMITS: BugAttachmentLimits = {
  maxFileMb: 10,
  maxFilesPerBug: 3,
  acceptedExtensions: ['.jpeg', '.jpg', '.pdf', '.png', '.xls', '.xlsx'],
}

/** Build a File of a given size without allocating the bytes twice. */
function fileOf(name: string, sizeBytes: number): File {
  const file = new File(['x'], name)
  // File.size is read-only; redefine it so tests can assert the size
  // rule without materialising megabytes of data.
  Object.defineProperty(file, 'size', { value: sizeBytes })
  return file
}

describe('fileExtension', () => {
  it.each([
    ['shot.png', '.png'],
    ['Report.PDF', '.pdf'],
    ['archive.tar.gz', '.gz'],
  ])('reads %s as %s', (name, expected) => {
    expect(fileExtension(name)).toBe(expected)
  })

  it.each(['noextension', '.gitignore', 'trailing.'])('returns empty for %s', (name) => {
    // A leading dot is a hidden-file name, not an extension, and a
    // trailing dot has nothing after it — neither should match.
    expect(fileExtension(name)).toBe('')
  })
})

describe('attachmentRejectionReason', () => {
  it('accepts a supported file within both limits', () => {
    expect(attachmentRejectionReason(fileOf('shot.png', 1024), LIMITS, 0)).toBeNull()
  })

  it('accepts a spreadsheet regardless of the browser-reported type', () => {
    // Browsers frequently label .xlsx as application/octet-stream; the
    // check is on the extension, so it must still pass.
    expect(attachmentRejectionReason(fileOf('export.xlsx', 2048), LIMITS, 0)).toBeNull()
  })

  it('rejects an unsupported extension and names the allowed set', () => {
    const reason = attachmentRejectionReason(fileOf('payload.exe', 10), LIMITS, 0)
    expect(reason).toContain('.pdf')
    expect(reason).toContain("isn't a supported type")
  })

  it('rejects a file over the size limit and reports its size', () => {
    const reason = attachmentRejectionReason(fileOf('big.pdf', 11 * 1024 * 1024), LIMITS, 0)
    expect(reason).toContain('11.0 MB')
    expect(reason).toContain('10 MB')
  })

  it('accepts a file exactly at the size limit', () => {
    expect(attachmentRejectionReason(fileOf('edge.pdf', 10 * 1024 * 1024), LIMITS, 0)).toBeNull()
  })

  it('rejects an empty file', () => {
    expect(attachmentRejectionReason(fileOf('empty.png', 0), LIMITS, 0)).toContain('is empty')
  })

  it('rejects once the per-bug count is reached', () => {
    const reason = attachmentRejectionReason(fileOf('shot.png', 10), LIMITS, 3)
    expect(reason).toContain('Limit of 3 files')
  })

  it('checks the count before the type, so a full bug says so first', () => {
    // Otherwise a reporter at the cap is told their file type is wrong,
    // which sends them off fixing the wrong thing.
    const reason = attachmentRejectionReason(fileOf('payload.exe', 10), LIMITS, 3)
    expect(reason).toContain('Limit of 3 files')
  })
})

describe('formatFileSize', () => {
  it.each([
    [512, '512 B'],
    [2048, '2 KB'],
    [1024 * 1024 * 2.5, '2.5 MB'],
  ])('formats %i as %s', (bytes, expected) => {
    expect(formatFileSize(bytes)).toBe(expected)
  })
})

describe('attachmentIcon', () => {
  it.each([
    ['application/pdf', 'mdi-file-pdf-box'],
    ['application/vnd.ms-excel', 'mdi-file-excel-box'],
    ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'mdi-file-excel-box'],
    ['application/unknown', 'mdi-file-outline'],
  ])('maps %s to %s', (mime, expected) => {
    expect(attachmentIcon(mime)).toBe(expected)
  })
})

describe('acceptAttribute', () => {
  it('builds a comma-separated accept list', () => {
    expect(acceptAttribute(LIMITS)).toBe('.jpeg,.jpg,.pdf,.png,.xls,.xlsx')
  })
})

describe('DEFAULT_ATTACHMENT_LIMITS', () => {
  it('matches the backend BugAttachmentSettings defaults', () => {
    // The staged picker in the create dialog runs on these before any
    // list response arrives — drift here means a misleading hint.
    expect(DEFAULT_ATTACHMENT_LIMITS.maxFileMb).toBe(10)
    expect(DEFAULT_ATTACHMENT_LIMITS.maxFilesPerBug).toBe(10)
    expect(DEFAULT_ATTACHMENT_LIMITS.acceptedExtensions).toEqual([
      '.jpeg',
      '.jpg',
      '.pdf',
      '.png',
      '.xls',
      '.xlsx',
    ])
  })
})
