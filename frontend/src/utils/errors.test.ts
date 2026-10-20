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
import { extractBlobApiError } from './errors'

const blobError = (status: number, body: unknown, type = 'application/json') => ({
  response: { status, data: new Blob([JSON.stringify(body)], { type }) },
})

describe('extractBlobApiError', () => {
  it("reads the server's reason out of a blob error body", async () => {
    const err = blobError(503, { detail: 'HR key not set.' })
    expect(await extractBlobApiError(err, 'fallback')).toBe('HR key not set.')
  })

  it('falls back when the body is not JSON', async () => {
    const err = blobError(500, 'oops', 'text/html')
    expect(await extractBlobApiError(err, 'fallback')).toBe('fallback')
  })

  it('still handles a normal JSON error', async () => {
    const err = { response: { status: 404, data: { detail: 'Not found.' } } }
    expect(await extractBlobApiError(err, 'fallback')).toBe('Not found.')
  })
})
