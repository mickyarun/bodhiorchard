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

import { ref, type Ref } from 'vue'
import { useBUDStore } from '@/stores/bud'
import type { BUDDocument } from '@/types'

/**
 * Reusable composable for editing a single markdown section of a BUD.
 * Encapsulates the editing/editValue/toggle/save pattern shared by
 * requirements_md, tech_spec_md, and test_plan_md tabs.
 */
export function useMarkdownSection(
  fieldName: keyof Pick<BUDDocument, 'requirements_md' | 'tech_spec_md' | 'test_plan_md'>,
  bud: Ref<BUDDocument | null>,
) {
  const budStore = useBUDStore()
  const editing = ref(false)
  const editValue = ref('')

  function toggle(): void {
    if (editing.value) {
      save()
    } else {
      editValue.value = bud.value?.[fieldName] || ''
      editing.value = true
    }
  }

  async function save(): Promise<void> {
    if (!bud.value) return
    if (editValue.value !== (bud.value[fieldName] || '')) {
      await budStore.updateBUD(bud.value.id, { [fieldName]: editValue.value })
    }
    editing.value = false
  }

  return { editing, editValue, toggle, save }
}
