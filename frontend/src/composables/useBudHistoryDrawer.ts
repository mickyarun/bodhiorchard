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

// The edit-history drawer, opened from the BUD header. It shows the
// history of the section on the open tab; tabs without an editable
// section (UAT, Prod, Closed) fall back to Requirements, which always
// has at least its first version.

import { ref, type Ref } from 'vue'

export type DiffSection = 'requirements' | 'tech-spec' | 'design' | 'testing' | 'code-review'

const DIFF_SECTIONS: ReadonlySet<string> = new Set<DiffSection>([
  'requirements', 'tech-spec', 'design', 'testing', 'code-review',
])

export function useBudHistoryDrawer(activeTab: Ref<string>) {
  const sectionDiffOpen = ref(false)
  const sectionDiffSection = ref<DiffSection>('requirements')

  function openHistory(): void {
    const tab = activeTab.value
    sectionDiffSection.value = DIFF_SECTIONS.has(tab) ? (tab as DiffSection) : 'requirements'
    sectionDiffOpen.value = true
  }

  return { sectionDiffOpen, sectionDiffSection, openHistory }
}
