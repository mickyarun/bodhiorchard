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

<!-- The header's overflow menu: move to any stage, restore a discarded
     BUD, open the AI skills settings, delete. -->
<template>
  <v-menu location="bottom end">
    <template #activator="{ props: menuProps }">
      <v-btn v-bind="menuProps" variant="outlined" icon="mdi-dots-horizontal" class="more-menu__btn" aria-label="More actions" />
    </template>
    <!-- A menu (the button says it opens one). The stages are a group of
         radio items, the current one checked; the rest are menu items. -->
    <v-list density="compact" min-width="200" role="menu" aria-label="More actions">
      <div role="group" aria-label="Change stage">
        <v-list-subheader aria-hidden="true">Change stage</v-list-subheader>
        <!-- Discarded is recoverable, closed is not: a closed BUD has already
             run its close-out (XP, SP, learning recap), and reopening it
             would let those fire again. -->
        <v-list-item
          v-if="status === 'discarded' && canEditBuds"
          role="menuitem"
          prepend-icon="mdi-restore"
          @click="emit('restore')"
        >
          <v-list-item-title>Restore BUD</v-list-item-title>
        </v-list-item>
        <v-list-item v-else-if="isClosed" role="menuitem" aria-disabled="true" disabled>
          <v-list-item-title class="text-medium-emphasis">
            {{ status === 'discarded' ? 'Discarded' : 'Closed' }}, so the stage can't change
          </v-list-item-title>
        </v-list-item>
        <template v-else>
          <v-list-item
            v-for="s in statusItems"
            :key="s.value"
            role="menuitemradio"
            :aria-checked="status === s.value"
            :aria-disabled="agentLocked || changingStatus || !canMoveTo(s.value)"
            :title="s.title"
            :active="status === s.value"
            :disabled="agentLocked || changingStatus || !canMoveTo(s.value)"
            @click="emit('update-status', s.value)"
          />
        </template>
      </div>
      <v-divider class="my-1" />
      <v-list-item
        role="menuitem"
        prepend-icon="mdi-tune-variant"
        :aria-disabled="isClosed"
        :disabled="isClosed"
        @click="emit('open-skill-settings')"
      >
        <v-list-item-title>AI skills</v-list-item-title>
      </v-list-item>
      <template v-if="canDelete">
        <v-divider class="my-1" />
        <v-list-item
          role="menuitem"
          base-color="error"
          prepend-icon="mdi-delete-outline"
          :aria-disabled="agentLocked"
          :disabled="agentLocked"
          @click="emit('delete')"
        >
          <v-list-item-title>Delete BUD</v-list-item-title>
        </v-list-item>
      </template>
    </v-list>
  </v-menu>
</template>

<script setup lang="ts">
import type { BUDStatus } from '@/types'

defineProps<{
  status: BUDStatus
  statusItems: ReadonlyArray<{ title: string; value: BUDStatus }>
  isClosed: boolean
  agentLocked: boolean
  changingStatus: boolean
  canEditBuds: boolean
  canMoveTo: (status: BUDStatus) => boolean
  canDelete: boolean
}>()

const emit = defineEmits<{
  'update-status': [status: BUDStatus]
  restore: []
  'open-skill-settings': []
  delete: []
}>()
</script>

<style scoped>
.more-menu__btn {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-input);
  border-color: rgb(var(--v-theme-rule));
}
</style>
