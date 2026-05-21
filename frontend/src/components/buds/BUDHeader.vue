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

<script setup lang="ts">
import { ref } from 'vue'
import { useMembersStore } from '@/stores/members'
import { BUD_STATUS_LABELS } from '@/types'
import type { BUDDocument, BUDStatus } from '@/types'
import { formatDate } from '@/utils/date'

const props = defineProps<{
  bud: BUDDocument
  statusColor: string
  statusItems: ReadonlyArray<{ title: string; value: BUDStatus }>
  isClosed: boolean
  agentLocked: boolean
  chatOpen: boolean
  // ``false`` when the active section isn't chattable in the current
  // BUD stage (mirrors the backend 409 gate). Locks the AI button so
  // the user can't even open the panel for a section that would be
  // rejected on first send.
  chatable: boolean
}>()

const emit = defineEmits<{
  back: []
  'update:chatOpen': [value: boolean]
  'change-assignee': [memberId: string | null]
  'update-status': [status: BUDStatus]
  delete: []
  'save-title': [title: string]
  'open-skill-settings': []
  'open-history': []
}>()

const membersStore = useMembersStore()

const editingTitle = ref(false)
const editTitle = ref('')
const assigneeSearch = ref('')

function startEditTitle(): void {
  if (props.agentLocked) return
  editTitle.value = props.bud.title
  editingTitle.value = true
}

function saveTitle(): void {
  const trimmed = editTitle.value.trim()
  if (!trimmed) {
    editingTitle.value = false
    return
  }
  if (trimmed !== props.bud.title) {
    emit('save-title', trimmed)
  }
  editingTitle.value = false
}
</script>

<template>
  <div class="bud-header">
    <div class="d-flex align-start ga-3 mb-1">
      <v-btn
        icon="mdi-arrow-left"
        variant="text"
        size="small"
        class="mt-1"
        @click="emit('back')"
      />
    <div class="flex-grow-1">
      <div class="d-flex align-center ga-2 mb-1 flex-wrap">
        <span class="text-caption text-medium-emphasis">
          BUD-{{ String(bud.bud_number).padStart(3, '0') }}
        </span>
        <v-chip :color="statusColor" variant="tonal" size="x-small" label>
          {{ BUD_STATUS_LABELS[bud.status] }}
        </v-chip>
        <v-menu location="bottom" :close-on-content-click="false">
          <template #activator="{ props: assigneeProps }">
            <v-chip
              v-bind="assigneeProps"
              :color="bud.assignee_name ? 'teal' : 'default'"
              variant="tonal"
              size="x-small"
              label
              class="cursor-pointer"
            >
              <v-icon start size="12">
                {{ bud.assignee_name ? 'mdi-account' : 'mdi-account-outline' }}
              </v-icon>
              {{ bud.assignee_name || 'Unassigned' }}
            </v-chip>
          </template>
          <v-card min-width="280" max-width="340" class="pa-2">
            <v-text-field
              v-model="assigneeSearch"
              variant="outlined"
              density="comfortable"
              placeholder="Search members..."
              hide-details
              prepend-inner-icon="mdi-magnify"
              class="mb-2"
              autofocus
            />
            <v-list max-height="280" class="overflow-y-auto">
              <v-list-item
                v-if="bud.assignee_id"
                @click="emit('change-assignee', null)"
              >
                <template #prepend>
                  <v-icon size="20" color="error">mdi-account-remove</v-icon>
                </template>
                <v-list-item-title class="text-body-2">Unassign</v-list-item-title>
              </v-list-item>
              <v-list-item
                v-for="m in membersStore.members.filter(
                  mm => mm.isActive && mm.name.toLowerCase().includes(assigneeSearch.toLowerCase())
                )"
                :key="m.id"
                :active="bud.assignee_id === m.id"
                @click="emit('change-assignee', m.id)"
              >
                <template #prepend>
                  <v-avatar size="28" color="surface-variant" class="mr-2">
                    <span class="text-body-2">{{ m.name.charAt(0).toUpperCase() }}</span>
                  </v-avatar>
                </template>
                <v-list-item-title class="text-body-2">{{ m.name }}</v-list-item-title>
                <v-list-item-subtitle class="text-caption">{{ m.role }}</v-list-item-subtitle>
              </v-list-item>
            </v-list>
          </v-card>
        </v-menu>
        <v-menu>
          <template #activator="{ props: menuProps }">
            <v-btn v-bind="menuProps" icon="mdi-dots-vertical" variant="text" size="x-small" />
          </template>
          <v-list density="compact" min-width="180">
            <v-list-subheader>Change Status</v-list-subheader>
            <v-list-item v-if="isClosed" disabled>
              <span class="text-caption text-medium-emphasis">
                {{ bud.status === 'discarded' ? 'Discarded' : 'Closed' }} — cannot change status
              </span>
            </v-list-item>
            <template v-else>
              <v-list-item
                v-for="s in statusItems"
                :key="s.value"
                :title="s.title"
                :active="bud.status === s.value"
                :disabled="agentLocked"
                @click="emit('update-status', s.value)"
              />
            </template>
            <v-divider class="my-1" />
            <v-list-item
              :disabled="isClosed"
              @click="emit('open-skill-settings')"
            >
              <div class="d-flex align-center">
                <v-icon icon="mdi-tune-variant" size="18" class="mr-2" />
                AI skills…
              </div>
            </v-list-item>
            <v-divider class="my-1" />
            <v-list-item
              base-color="error"
              class="delete-item"
              :disabled="agentLocked"
              @click="emit('delete')"
            >
              <div class="d-flex align-center">
                <v-icon icon="mdi-delete-outline" size="18" class="mr-2" />
                Delete BUD
              </div>
            </v-list-item>
          </v-list>
        </v-menu>
        <v-btn
          variant="tonal"
          size="x-small"
          class="header-action-btn"
          title="View edit history and restore previous versions"
          @click="emit('open-history')"
        >
          <v-icon start size="14">mdi-history</v-icon>
          History
        </v-btn>
        <v-btn
          :variant="chatOpen ? 'flat' : 'tonal'"
          :color="chatOpen ? 'primary' : 'default'"
          size="x-small"
          class="header-action-btn ai-chat-btn"
          :disabled="agentLocked || !chatable"
          :title="!chatable && !agentLocked
            ? 'Chat is not available for this section in the current stage.'
            : ''"
          @click="emit('update:chatOpen', !chatOpen)"
        >
          <v-icon start size="14">mdi-creation-outline</v-icon>
          AI
        </v-btn>
      </div>
      <div
        v-if="!editingTitle"
        class="text-h5 font-weight-bold"
        :class="agentLocked ? 'prd-locked-title' : 'cursor-pointer'"
        @click="startEditTitle"
      >
        {{ bud.title }}
      </div>
      <v-text-field
        v-else
        v-model="editTitle"
        variant="outlined"
        density="compact"
        autofocus
        hide-details
        class="mt-1"
        style="max-width: 500px;"
        @blur="saveTitle"
        @keyup.enter="saveTitle"
        @keyup.escape="editingTitle = false"
      />
    </div>
  </div>

    <div class="text-caption text-medium-emphasis mb-3 ml-12">
      Created {{ formatDate(bud.created_at) }} &middot; Updated {{ formatDate(bud.updated_at) }}
    </div>
  </div>
</template>

<style scoped>
.header-action-btn {
  text-transform: none;
  letter-spacing: 0;
  font-weight: 600;
  font-size: 13px;
}
.ai-chat-btn {
  text-transform: none;
  letter-spacing: 0;
  font-weight: 600;
  font-size: 13px;
}

.prd-locked-title {
  opacity: 0.5;
  pointer-events: none;
}
</style>
