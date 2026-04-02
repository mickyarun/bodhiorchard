import { ref } from 'vue'
import type { BUDEstimates } from '@/types'
import { useBUDStore } from '@/stores/bud'

export function useEstimates(getBudId: () => string | undefined) {
  const budStore = useBUDStore()

  const budEstimates = ref<BUDEstimates | null>(null)
  const estimatesLoading = ref(false)
  const recalculating = ref(false)

  // Override dialog state
  const overrideDialogOpen = ref(false)
  const overridePhase = ref('')
  const overrideDate = ref('')
  const overrideReason = ref('')

  async function loadEstimates(): Promise<void> {
    const budId = getBudId()
    if (!budId) return
    estimatesLoading.value = true
    budEstimates.value = await budStore.fetchEstimates(budId)
    estimatesLoading.value = false
  }

  async function handleRecalculate(): Promise<void> {
    const budId = getBudId()
    if (!budId) return
    recalculating.value = true
    budEstimates.value = await budStore.recalculateEstimates(budId)
    recalculating.value = false
  }

  function openOverrideDialog(phase: string): void {
    overridePhase.value = phase
    overrideDate.value = ''
    overrideReason.value = ''
    overrideDialogOpen.value = true
  }

  async function submitOverride(): Promise<void> {
    const budId = getBudId()
    if (!budId || !overrideDate.value || !overrideReason.value.trim()) return
    await budStore.overrideEstimate(
      budId,
      overridePhase.value,
      overrideDate.value,
      overrideReason.value,
    )
    overrideDialogOpen.value = false
    await loadEstimates()
  }

  return {
    budEstimates,
    estimatesLoading,
    recalculating,
    overrideDialogOpen,
    overridePhase,
    overrideDate,
    overrideReason,
    loadEstimates,
    handleRecalculate,
    openOverrideDialog,
    submitOverride,
  }
}
