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
 * Tests for the bug-attachment composable, focused on the per-bug cap.
 *
 * The cap is counted client-side against `items`, and the create dialog
 * reuses a single composable instance for every bug filed in a page
 * session — the dialog never unmounts. That combination is what makes
 * the list's ownership worth pinning down here rather than leaving it
 * to the component tests.
 *
 * `.spec.ts` (not `.test.ts`) because vitest.config.ts maps that suffix
 * to jsdom, and these need `File` and `FormData`.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'

const apiGet = vi.fn()
const apiPost = vi.fn()
const apiDelete = vi.fn()
vi.mock('@/services/api', () => ({
  default: { get: apiGet, post: apiPost, delete: apiDelete },
}))

const { useBugAttachments } = await import('./useBugAttachments')

const LIMITS = {
  maxFileMb: 10,
  maxFilesPerBug: 3,
  acceptedExtensions: ['.jpeg', '.jpg', '.pdf', '.png', '.xls', '.xlsx'],
}

let storedId = 0

function file(name: string): File {
  return new File(['x'], name, { type: 'image/png' })
}

beforeEach(() => {
  storedId = 0
  apiGet.mockReset()
  apiPost.mockReset()
  apiDelete.mockReset()
  apiGet.mockResolvedValue({ data: { items: [], limits: LIMITS } })
  apiPost.mockImplementation(async () => ({
    data: {
      id: `att-${++storedId}`,
      filename: `f${storedId}.png`,
      mimeType: 'image/png',
      sizeBytes: 1,
      uploadedBy: null,
      createdAt: '2026-09-23T00:00:00Z',
    },
  }))
  apiDelete.mockResolvedValue({ data: {} })
})

describe('per-bug cap', () => {
  it('counts only the bug being uploaded to, not earlier ones', async () => {
    // The regression: the create dialog files bug after bug through one
    // composable instance. If `items` carries over, the second report is
    // rejected as "limit reached" while having no attachments at all —
    // and its "Retry upload" can never succeed, because the retry hits
    // the same stale count.
    const a = useBugAttachments()
    await a.load('bug-1')
    await a.uploadMany('bug-1', [file('a.png'), file('b.png'), file('c.png')])
    expect(a.items.value).toHaveLength(3)

    const stored = await a.uploadMany('bug-2', [file('d.png')])

    expect(stored).toHaveLength(1)
    expect(a.error.value).toBeNull()
    expect(a.items.value).toHaveLength(1)
  })

  it('still enforces the cap within a single bug', async () => {
    const a = useBugAttachments()
    await a.load('bug-1')
    const stored = await a.uploadMany('bug-1', [
      file('a.png'),
      file('b.png'),
      file('c.png'),
      file('d.png'),
    ])

    // uploadMany stops at the first failure, so the successes are the
    // leading slice — which is what the dialog's flush() relies on when
    // it drops stored files from the staged list.
    expect(stored).toHaveLength(3)
    expect(apiPost).toHaveBeenCalledTimes(3)
    expect(a.error.value).toContain('Limit of 3 files')
  })

  it('reloading the same bug does not double-count', async () => {
    const a = useBugAttachments()
    await a.load('bug-1')
    await a.uploadMany('bug-1', [file('a.png')])
    apiGet.mockResolvedValue({
      data: { items: [{ id: 'att-1', filename: 'a.png' }], limits: LIMITS },
    })
    await a.load('bug-1')

    expect(a.items.value).toHaveLength(1)
  })
})

describe('client-side validation', () => {
  it('rejects an unsupported type without calling the API', async () => {
    const a = useBugAttachments()
    await a.load('bug-1')
    const stored = await a.upload('bug-1', new File(['x'], 'payload.exe'))

    expect(stored).toBeNull()
    expect(apiPost).not.toHaveBeenCalled()
    expect(a.error.value).toContain("isn't a supported type")
  })
})

describe('remove', () => {
  it('drops the row locally once the API confirms', async () => {
    const a = useBugAttachments()
    await a.load('bug-1')
    await a.uploadMany('bug-1', [file('a.png'), file('b.png')])

    expect(await a.remove('bug-1', 'att-1')).toBe(true)
    expect(a.items.value.map((i) => i.id)).toEqual(['att-2'])
  })

  it('keeps the row when the API rejects the delete', async () => {
    const a = useBugAttachments()
    await a.load('bug-1')
    await a.uploadMany('bug-1', [file('a.png')])
    apiDelete.mockRejectedValue(new Error('boom'))

    expect(await a.remove('bug-1', 'att-1')).toBe(false)
    expect(a.items.value).toHaveLength(1)
  })
})
