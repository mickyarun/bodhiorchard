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
