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
import { templateForAgent } from './customSkillForm.util'
import {
  applyParsedImport,
  importToastMessage,
  parseFrontmatter,
  slugifyName,
  splitListValue,
} from './customSkillImport.util'

const FILE = [
  '---',
  'name: "Concise PM"',
  'description: Short PRDs',
  'tools: Read, Write Edit',
  'model: opus',
  'max_turns: 7',
  '__proto__: polluted',
  '---',
  '',
  '# Body',
].join('\n')

describe('parseFrontmatter', () => {
  it('splits known keys from the body and ignores the rest', () => {
    const parsed = parseFrontmatter(FILE)
    expect(parsed?.meta).toEqual({
      name: 'Concise PM', description: 'Short PRDs', tools: 'Read, Write Edit', model: 'opus', max_turns: '7',
    })
    expect(parsed?.body).toBe('# Body')
  })

  it('returns null without frontmatter', () => {
    expect(parseFrontmatter('# Just a prompt')).toBeNull()
  })
})

describe('helpers', () => {
  it('splits lists on commas and whitespace', () => {
    expect(splitListValue('Read, Write  Edit')).toEqual(['Read', 'Write', 'Edit'])
  })

  it('slugifies a display name', () => {
    expect(slugifyName('  Concise -- PM! ')).toBe('concise-pm')
  })

  it('words the toast by source and count', () => {
    expect(importToastMessage('file', 1)).toBe('Imported 1 field from file')
    expect(importToastMessage('paste', 3)).toBe('Stripped frontmatter and split 3 fields')
  })
})

describe('applyParsedImport', () => {
  it('fills the form in place and reports the touched fields', () => {
    const form = templateForAgent([], 'bud')
    const touched = applyParsedImport(form, parseFrontmatter(FILE)!)
    expect(touched).toEqual(['name', 'slug', 'description', 'tools', 'model', 'max_turns'])
    expect(form).toMatchObject({
      name: 'Concise PM', skillSlug: 'concise-pm', tools: ['Read', 'Write', 'Edit'], model: 'opus', maxTurns: 7, prompt: '# Body',
    })
  })

  it('keeps an existing slug and skips an unknown model', () => {
    const form = { ...templateForAgent([], 'bud'), skillSlug: 'mine' }
    const touched = applyParsedImport(form, { meta: { name: 'X', model: 'gpt-9' }, body: '' })
    expect(touched).toEqual(['name'])
    expect(form.skillSlug).toBe('mine')
    expect(form.model).toBe('')
  })
})
