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
import type { BugAttachment } from '@/types'
import { attachmentHint, stagedTiles, storedTiles } from './attachmentTiles'

describe('stagedTiles', () => {
  it('keys picked files by position, name and modified time', () => {
    const file = new File(['x'], 'shot.png', { type: 'image/png', lastModified: 7 })
    expect(stagedTiles([file])).toEqual([
      { key: '0-shot.png-7', filename: 'shot.png', mimeType: 'image/png', sizeBytes: 1, fetchPath: null, file },
    ])
  })
})

describe('storedTiles', () => {
  it('keys stored attachments by id with their download path', () => {
    const item = { id: 'a1', filename: 'log.txt', mimeType: 'text/plain', sizeBytes: 12 } as BugAttachment
    expect(storedTiles([item], id => `/dl/${id}`)).toEqual([
      { key: 'a1', filename: 'log.txt', mimeType: 'text/plain', sizeBytes: 12, fetchPath: '/dl/a1', file: null },
    ])
  })
})

describe('attachmentHint', () => {
  it('states the count, size and type limits', () => {
    const limits = { maxFilesPerBug: 5, maxFileMb: 10, acceptedExtensions: ['png', 'pdf'] }
    expect(attachmentHint(limits)).toBe('Up to 5 files, 10 MB each (png, pdf).')
  })
})
