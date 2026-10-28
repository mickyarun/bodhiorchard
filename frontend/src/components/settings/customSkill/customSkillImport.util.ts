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
 * .md import for the "New custom skill" dialog.
 *
 * Skill files in the wild (Claude Code catalog, anthropics samples, etc.)
 * are shaped like:
 *
 *   ---
 *   name: foo
 *   description: …
 *   tools: Read, Write
 *   ---
 *
 *   # Foo
 *   You are …
 *
 * The "tools" line is sometimes comma-separated, sometimes whitespace.
 * We strip the frontmatter, split it into the form's metadata fields,
 * and put the body in the Prompt field — same shape we expect from
 * users authoring from scratch.
 */

import { CUSTOM_SKILL_MODEL_OPTIONS, type CustomSkillForm } from './customSkillForm.util'

// Parsed frontmatter — only the six fields we consume downstream.
// Optional because any field may be absent from a real file.
export interface ParsedMeta {
  name?: string
  description?: string
  tools?: string
  mcp_tools?: string
  model?: string
  max_turns?: string
}

export interface ParsedFrontmatter {
  meta: ParsedMeta
  body: string
}

export type ImportSource = 'file' | 'paste'

const MODEL_VALUES = new Set(CUSTOM_SKILL_MODEL_OPTIONS.map(o => o.value))

function stripQuotes(value: string): string {
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    return value.slice(1, -1)
  }
  return value
}

export function parseFrontmatter(text: string): ParsedFrontmatter | null {
  const match = text.match(/^---\s*\r?\n([\s\S]*?)\r?\n---\s*\r?\n?([\s\S]*)$/)
  if (!match) return null
  const yamlBlock = match[1]
  const body = match[2] ?? ''
  // Explicit switch on literal keys instead of ``meta[userKey] = value``.
  // The dynamic-property-write form (even guarded by a runtime Set.has)
  // tripped CodeQL's "Remote property injection" rule, since a malicious
  // .md with ``__proto__: …`` or ``constructor: …`` lines would be
  // tainted user input flowing into a property name. With a switch the
  // assignment targets are compile-time literals — there's no dataflow
  // edge for CodeQL to flag, and unknown keys are dropped on the floor.
  const meta: ParsedMeta = {}
  for (const line of yamlBlock.split(/\r?\n/)) {
    const kv = line.match(/^([a-zA-Z_][a-zA-Z0-9_-]*)\s*:\s*(.*)$/)
    if (!kv) continue
    const key = kv[1]
    const value = stripQuotes(kv[2].trim())
    switch (key) {
      case 'name':
        meta.name = value
        break
      case 'description':
        meta.description = value
        break
      case 'tools':
        meta.tools = value
        break
      case 'mcp_tools':
        meta.mcp_tools = value
        break
      case 'model':
        meta.model = value
        break
      case 'max_turns':
        meta.max_turns = value
        break
      // any other key (incl. __proto__, constructor) is silently ignored
    }
  }
  return { meta, body: body.replace(/^\r?\n+/, '') }
}

export function splitListValue(value: string): string[] {
  return value
    .split(/[,\s]+/)
    .map(s => s.trim())
    .filter(Boolean)
}

export function slugifyName(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .replace(/-{2,}/g, '-')
}

/**
 * Writes the parsed frontmatter and body into ``form`` in place and returns
 * the names of the metadata fields it filled.
 */
export function applyParsedImport(form: CustomSkillForm, parsed: ParsedFrontmatter): string[] {
  const { meta, body } = parsed
  const touched: string[] = []

  if (meta.name) {
    form.name = meta.name
    touched.push('name')
    if (!form.skillSlug) {
      form.skillSlug = slugifyName(meta.name)
      touched.push('slug')
    }
  }
  if (meta.description) {
    form.description = meta.description
    touched.push('description')
  }
  if (meta.tools) {
    form.tools = splitListValue(meta.tools)
    touched.push('tools')
  }
  if (meta.mcp_tools) {
    form.mcpTools = splitListValue(meta.mcp_tools)
    touched.push('mcp_tools')
  }
  if (meta.model && MODEL_VALUES.has(meta.model)) {
    form.model = meta.model
    touched.push('model')
  }
  if (meta.max_turns) {
    const n = Number(meta.max_turns)
    if (Number.isFinite(n)) {
      form.maxTurns = n
      touched.push('max_turns')
    }
  }

  form.prompt = body
  return touched
}

export function importToastMessage(source: ImportSource, touchedCount: number): string {
  const fields = `${touchedCount} field${touchedCount === 1 ? '' : 's'}`
  return source === 'file'
    ? `Imported ${fields} from file`
    : `Stripped frontmatter and split ${fields}`
}
