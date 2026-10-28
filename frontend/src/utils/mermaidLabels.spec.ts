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

// A spec (jsdom) rather than a test: Mermaid's parser needs a DOM, and
// parsing the output for real is the point.
import mermaid from 'mermaid'
import { describe, expect, it } from 'vitest'

import { quoteMermaidLabels } from '@/utils/mermaidLabels'

const parses = (source: string): Promise<unknown> =>
  mermaid.parse(source, { suppressErrors: true })

describe('quoteMermaidLabels', () => {
  it('quotes a node label with quotes inside so it parses', async () => {
    const source = 'flowchart TD\n  J --> K[Show snoozed pill, "n of 3" count, Clear link]'
    expect(await parses(source)).toBe(false)
    const fixed = quoteMermaidLabels(source)
    expect(fixed).toBe(
      'flowchart TD\n  J --> K["Show snoozed pill, #quot;n of 3#quot; count, Clear link"]',
    )
    expect(await parses(fixed)).toBeTruthy()
  })

  it('handles other node shapes and edge labels', async () => {
    const source = [
      'graph LR',
      '  A("Say "hi"") -->|reply "ok"| B{Is it "done"?}',
      '  B -- pick "yes" --> C([End "here"])',
    ].join('\n')
    const fixed = quoteMermaidLabels(source)
    expect(fixed).toBe(
      [
        'graph LR',
        '  A("Say #quot;hi#quot;") -->|"reply #quot;ok#quot;"| B{"Is it #quot;done#quot;?"}',
        '  B -- "pick #quot;yes#quot;" --> C(["End #quot;here#quot;"])',
      ].join('\n'),
    )
    expect(await parses(fixed)).toBeTruthy()
  })

  it('leaves labels that are already valid as written', () => {
    const source = [
      'flowchart TD',
      '  A[Start] --> B["Quoted, fine"]',
      '  B -->|yes| C(Done)',
      '  C --> D["items[0]"] --> E("Retry (3x)")',
    ].join('\n')
    expect(quoteMermaidLabels(source)).toBe(source)
  })

  it('leaves other diagram types alone', () => {
    const source = 'sequenceDiagram\n  A->>B: say "hi" (now)'
    expect(quoteMermaidLabels(source)).toBe(source)
  })
})
