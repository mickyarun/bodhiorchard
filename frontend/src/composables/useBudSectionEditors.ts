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

// The Requirements and Tech spec editors plus the Design panel's editor,
// behind the section toolbar's one Edit toggle.

import { computed, type ComputedRef, type Ref } from 'vue'
import { useMarkdownSection } from '@/composables/useMarkdownSection'
import type { BUDDocument } from '@/types'

export interface DesignEditor {
  editingDesignId: string | null
  toggleDesignEdit: () => void
}

export function useBudSectionEditors(
  bud: ComputedRef<BUDDocument | null>,
  activeTab: Ref<string>,
  editable: ComputedRef<boolean>,
  getDesignEditor: () => DesignEditor | null,
) {
  const requirements = useMarkdownSection('requirements_md', bud)
  const techSpec = useMarkdownSection('tech_spec_md', bud)

  const isEditing = computed(() => {
    if (activeTab.value === 'tech-spec') return techSpec.editing.value
    if (activeTab.value === 'design') return getDesignEditor()?.editingDesignId !== null
    return requirements.editing.value
  })

  // Honours the same stage rule as the toolbar's Edit button.
  function toggleEdit(): void {
    if (!editable.value) return
    if (activeTab.value === 'tech-spec') techSpec.toggle()
    else if (activeTab.value === 'design') getDesignEditor()?.toggleDesignEdit()
    else requirements.toggle()
  }

  /** Mirror an AI chat edit into the open editor so unsaved typing isn't stale. */
  function syncEditor(section: string, content: string): void {
    if (section === 'requirements_md' && requirements.editing.value) requirements.editValue.value = content
    else if (section === 'tech_spec_md' && techSpec.editing.value) techSpec.editValue.value = content
  }

  return { requirements, techSpec, isEditing, toggleEdit, syncEditor }
}
