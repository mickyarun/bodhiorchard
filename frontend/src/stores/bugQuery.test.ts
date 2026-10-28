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
import { BUG_BOARD_COLUMNS } from '@/types'
import { bugBoardParams, bugListParams, emptyBoard } from './bugQuery'

describe('emptyBoard', () => {
  it('has an empty list for every column', () => {
    const board = emptyBoard()
    expect(Object.keys(board)).toEqual([...BUG_BOARD_COLUMNS])
    expect(Object.values(board).every(col => col.length === 0)).toBe(true)
  })
})

describe('bugListParams', () => {
  it('falls back to the current page and leaves out unset filters', () => {
    expect(bugListParams({ budId: 'b1' }, 3, 20)).toEqual({ budId: 'b1', page: 3, pageSize: 20 })
  })
  it('prefers the page asked for', () => {
    expect(bugListParams({ page: 1, pageSize: 100, status: 'open' }, 3, 20))
      .toEqual({ status: 'open', page: 1, pageSize: 100 })
  })
})

describe('bugBoardParams', () => {
  it('passes only the filters that are set', () => {
    expect(bugBoardParams(undefined)).toEqual({})
    expect(bugBoardParams({ bugType: 'all', severity: '' })).toEqual({ bugType: 'all' })
  })
})
