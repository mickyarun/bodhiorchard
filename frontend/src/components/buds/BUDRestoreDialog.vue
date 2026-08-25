<!--
  Copyright 2025-2026 Arun Rajkumar

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.
-->

<!--
  Confirm-and-restore for a discarded BUD.

  Owns the whole interaction — confirmation, the store call, and the
  result snackbar — so the board and the BUD detail page get identical
  behaviour from one `<BUDRestoreDialog ref="…" />` plus an `open(bud)`
  call. Both entry points reach the same discarded BUDs, so the two
  copies of this flow would have to be kept in step by hand otherwise.

  The landing phase is decided server-side (whatever the BUD was
  discarded from), which is why the confirmation copy stays general and
  the snackbar reports where it actually went.
-->
<template>
  <div>
    <v-dialog v-model="dialogOpen" max-width="440">
      <v-card color="surface" class="pa-6">
        <div class="text-h6 font-weight-bold mb-2">Restore BUD?</div>
        <div class="text-body-2 text-medium-emphasis mb-4">
          <strong>{{ targetLabel }}</strong> goes back into the pipeline at the
          phase it was in when it was discarded, and its linked feature becomes
          active again. Delivery dates are cleared — the next estimate works
          them out from where it restarts.
        </div>
        <v-card-actions class="pa-0">
          <v-spacer />
          <v-btn variant="text" :disabled="restoring" @click="dialogOpen = false">Cancel</v-btn>
          <v-btn color="primary" variant="flat" :loading="restoring" @click="confirm">
            Restore
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackbar" :color="isError ? 'error' : 'success'" :timeout="4000">
      {{ message }}
    </v-snackbar>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useBUDStore } from '@/stores/bud'
import { BUD_STATUS_LABELS } from '@/types'
import type { BUDDocument, BUDListItem } from '@/types'

const emit = defineEmits<{
  /** Fired after a successful restore, with the updated BUD. */
  restored: [bud: BUDDocument]
}>()

const budStore = useBUDStore()

const dialogOpen = ref(false)
const target = ref<BUDListItem | null>(null)
const restoring = ref(false)
const snackbar = ref(false)
const message = ref('')
const isError = ref(false)

const targetLabel = computed(() => (target.value ? budRef(target.value) : ''))

function budRef(bud: BUDListItem): string {
  return `BUD-${String(bud.bud_number).padStart(3, '0')}`
}

/** Open the confirmation for one discarded BUD. */
function open(bud: BUDListItem): void {
  target.value = bud
  dialogOpen.value = true
}

async function confirm(): Promise<void> {
  const bud = target.value
  if (!bud) return
  restoring.value = true
  try {
    const result = await budStore.restoreBUD(bud.id)
    isError.value = result === null
    // The store swaps the row in ``buds`` and ``currentBUD``, so the board
    // card moves column and the detail page re-renders on its own — the
    // only thing left is telling the user where the BUD went.
    message.value = result
      ? `${budRef(bud)} restored to ${BUD_STATUS_LABELS[result.status]}`
      : budStore.error || 'Failed to restore BUD'
    snackbar.value = true
    if (result) emit('restored', result)
  } finally {
    restoring.value = false
    dialogOpen.value = false
    target.value = null
  }
}

defineExpose({ open })
</script>
