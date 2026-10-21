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

import { credentialsMailto } from '@/utils/credentialsMail'

describe('credentialsMailto', () => {
  it('addresses the person and encodes the details so symbols survive', () => {
    const link = credentialsMailto({ name: 'Ravi', email: 'ravi@co.com', password: 'a&b#C1', loginUrl: 'https://app/login' })
    expect(link.startsWith('mailto:ravi@co.com?subject=')).toBe(true)
    const body = decodeURIComponent(link.split('&body=')[1])
    expect(body).toContain('Temporary Password: a&b#C1')
    expect(body).toContain('Log in here: https://app/login')
  })
})
