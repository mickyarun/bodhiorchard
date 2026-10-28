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
 * Quote flowchart labels that contain a plain double quote.
 *
 * ``K[Show "n of 3" count]`` and ``A -->|say "hi"| B`` are Mermaid syntax
 * errors: a ``"`` may only wrap a whole label. The fix Mermaid documents is
 * to quote the label and write the inner quotes as ``#quot;``, which still
 * draws as ``"``. Labels without a quote, already-quoted labels and other
 * diagram types are returned exactly as written. It is a repair for a
 * diagram that fails to parse, not a formatter: the renderer only uses it
 * when the source as written doesn't parse.
 */

// Openers and their closers, longest first so ``([`` wins over ``(``.
const NODE_SHAPES: ReadonlyArray<readonly [string, string]> = [
  ['([', '])'],
  ['[[', ']]'],
  ['[(', ')]'],
  ['((', '))'],
  ['{{', '}}'],
  ['[', ']'],
  ['(', ')'],
  ['{', '}'],
]

const escapeRegExp = (text: string): string => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

// A node id, then one label shape: ``K[...]``, ``B(...)``, ``C{{...}}``. A
// whole quoted label is taken as one piece first, so brackets inside it
// (``A["items[0]"]``) don't end it early.
const NODE_LABEL = new RegExp(
  `(\\b[A-Za-z0-9_]+)(?:${NODE_SHAPES.map(
    ([open, close]) => `${escapeRegExp(open)}("[^"\\n]*"|.*?)${escapeRegExp(close)}`,
  ).join('|')})`,
  'g',
)
// ``-->|text|`` and ``-- text -->``.
const PIPE_LABEL = /\|([^|\n]*)\|/g
const DASH_LABEL = /(\s--\s+)(.*?)(\s+-->)/g
const WRAPPED = /^\s*"(.*)"\s*$/
const FLOWCHART = /^\s*(flowchart|graph)\b/

/** ``label`` quoted with its inner quotes escaped, or null when it is fine as written. */
function quoted(label: string): string | null {
  if (!label.includes('"')) return null
  const inner = label.match(WRAPPED)?.[1] ?? label
  if (!inner.includes('"')) return null
  return `"${inner.replace(/"/g, '#quot;')}"`
}

function quoteLine(line: string): string {
  if (line.trimStart().startsWith('%%')) return line
  return line
    .replace(NODE_LABEL, (match: string, id: string, ...groups: unknown[]) => {
      // One capture group per shape; the one that matched holds the label.
      const index = groups.findIndex(g => typeof g === 'string')
      const shape = NODE_SHAPES[index]
      const label = shape ? quoted(groups[index] as string) : null
      return shape && label !== null ? `${id}${shape[0]}${label}${shape[1]}` : match
    })
    .replace(PIPE_LABEL, (match: string, text: string) => {
      const label = quoted(text)
      return label === null ? match : `|${label}|`
    })
    .replace(DASH_LABEL, (match: string, start: string, text: string, end: string) => {
      const label = quoted(text)
      return label === null ? match : `${start}${label}${end}`
    })
}

/** ``source`` with every flowchart label that holds a stray ``"`` quoted. */
export function quoteMermaidLabels(source: string): string {
  const lines = source.split('\n')
  const firstLine = lines.find(line => line.trim() !== '') ?? ''
  if (!FLOWCHART.test(firstLine)) return source
  return lines.map(quoteLine).join('\n')
}
