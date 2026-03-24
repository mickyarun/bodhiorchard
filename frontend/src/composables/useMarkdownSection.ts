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
