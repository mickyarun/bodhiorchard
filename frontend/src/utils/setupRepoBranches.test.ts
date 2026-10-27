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

import { needsPathBranchLookup } from './setupRepoBranches'

describe('needsPathBranchLookup', () => {
  it('looks up a picked local folder whose branches are not known yet', () => {
    expect(needsPathBranchLookup('local-path', undefined)).toBe(true)
  })

  it('skips a local folder already validated, even when it has no develop', () => {
    expect(needsPathBranchLookup('local-path', 'develop')).toBe(false)
    expect(needsPathBranchLookup('local-path', null)).toBe(false)
  })

  it('never looks up a clone by path, which in Docker lies outside the picker roots', () => {
    expect(needsPathBranchLookup('github-clone', undefined)).toBe(false)
    expect(needsPathBranchLookup('github-clone', null)).toBe(false)
  })

  it('never looks up a bulk-imported repo by path', () => {
    expect(needsPathBranchLookup('bulk', undefined)).toBe(false)
  })
})
