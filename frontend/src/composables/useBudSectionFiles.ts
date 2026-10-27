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

// Export a BUD section to a file, or import one into it. Markdown sections
// save as .md; the Design tab saves the open design's HTML.

import type { ComputedRef } from 'vue'
import { useBUDStore } from '@/stores/bud'
import { budRef, type BUDDocument } from '@/types'
import { saveBlob } from '@/utils/download'

export interface ActiveDesign {
  design_html?: string | null
  repo_name?: string | null
}

export function useBudSectionFiles(
  bud: ComputedRef<BUDDocument | null>,
  getActiveDesign: () => ActiveDesign | null | undefined,
) {
  const budStore = useBUDStore()

  function downloadSection(section: string): void {
    if (!bud.value) return
    const ref = budRef(bud.value.bud_number)
    if (section === 'design') {
      const design = getActiveDesign()
      if (!design?.design_html) return
      saveBlob(new Blob([design.design_html], { type: 'text/html' }), `${ref}-design-${design.repo_name || 'default'}.html`)
      return
    }
    const content = ((bud.value as unknown as Record<string, unknown>)[section] as string) || ''
    const suffix = section.replace('_md', '').replace('_', '-')
    saveBlob(new Blob([content], { type: 'text/markdown' }), `${ref}-${suffix}.md`)
  }

  async function importSection(section: string, file: File): Promise<void> {
    if (!bud.value) return
    await budStore.importBUD(bud.value.id, section, file)
  }

  return { downloadSection, importSection }
}
