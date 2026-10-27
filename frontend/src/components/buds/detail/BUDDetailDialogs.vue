<!--
 * Copyright 2025-2026 Arun Rajkumar
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 -->

<!-- The BUD detail page's dialogs and drawers: restore, the stage-change
     guards, AI skills, edit history and delete. All of them teleport to
     the overlay layer, so where this mounts doesn't affect layout. -->
<template>
  <!-- Shared with the board, so restore behaves the same from both. -->
  <BUDRestoreDialog ref="restoreDialog" @restored="emit('restored')" />
  <BUDStatusDialogs :controller="controller" />
  <template v-if="bud">
    <!-- The page refetches on save so the banner and the next stage change
         see the new auto_generate_phases. -->
    <BUDSkillSettingsDialog
      v-model="skillSettingsOpen"
      :bud-id="bud.id"
      :auto-generate-phases="bud.auto_generate_phases ?? null"
      @saved="emit('settings-saved')"
    />
    <BUDSectionDiffDrawer
      v-model="historyOpen"
      :bud-id="bud.id"
      :bud-status="bud.status"
      :section="historySection"
      @reverted="emit('reverted')"
    />
    <BUDDeleteDialog v-model="deleteOpen" :bud="bud" @confirm="emit('confirm-delete')" />
  </template>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import BUDRestoreDialog from '@/components/buds/BUDRestoreDialog.vue'
import BUDSectionDiffDrawer from '@/components/buds/BUDSectionDiffDrawer.vue'
import BUDSkillSettingsDialog from '@/components/buds/BUDSkillSettingsDialog.vue'
import BUDStatusDialogs from '@/components/buds/BUDStatusDialogs.vue'
import BUDDeleteDialog from './BUDDeleteDialog.vue'
import type { useBudStatusTransitions } from '@/composables/useBudStatusTransitions'
import type { DiffSection } from '@/composables/useBudHistoryDrawer'
import type { BUDDocument, BUDListItem } from '@/types'

defineProps<{
  bud: BUDDocument | null
  controller: ReturnType<typeof useBudStatusTransitions>
  historySection: DiffSection
}>()

const emit = defineEmits<{
  restored: []
  'settings-saved': []
  reverted: []
  'confirm-delete': []
}>()

const skillSettingsOpen = defineModel<boolean>('skillSettingsOpen', { required: true })
const historyOpen = defineModel<boolean>('historyOpen', { required: true })
const deleteOpen = defineModel<boolean>('deleteOpen', { required: true })

const restoreDialog = ref<InstanceType<typeof BUDRestoreDialog> | null>(null)

/** Ask to restore a discarded BUD. */
function openRestore(bud: BUDListItem): void {
  restoreDialog.value?.open(bud)
}

defineExpose({ openRestore })
</script>
