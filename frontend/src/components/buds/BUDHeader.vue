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

<!-- BUD detail header: breadcrumb, reference / priority / stage, the
     title (click to rename), who owns it and when it moved, and the
     actions: history, AI chat, move to the next stage, and the overflow
     menu. -->
<template>
  <header class="bud-header">
    <nav aria-label="Breadcrumb" class="bud-header__crumbs">
      <router-link to="/buds">Board</router-link>
      <span aria-hidden="true">/</span>
      <span aria-current="page" class="bud-header__mono">{{ budRef(bud.bud_number) }}</span>
    </nav>

    <div class="bud-header__row">
      <div class="bud-header__main">
        <div class="bud-header__tags">
          <span class="bud-header__mono">{{ budRef(bud.bud_number) }}</span>
          <BUDPriorityMenu :priority="bud.priority" :editable="canEditPriority" @change="emit('change-priority', $event)" />
          <span class="bud-header__stage" :style="{ '--stage': `var(--v-theme-${BUD_STATUS_COLORS[bud.status]})` }">
            <span class="bud-header__stage-dot" />{{ BUD_STATUS_LABELS[bud.status] }}
          </span>
        </div>

        <h1 v-if="!editingTitle" class="bud-header__title">
          <button
            type="button"
            class="bud-header__title-btn"
            :disabled="agentLocked"
            :title="agentLocked ? undefined : 'Rename'"
            @click="startEditTitle"
          >
            {{ bud.title }}<span class="d-sr-only">, rename</span>
            <v-icon v-if="!agentLocked" icon="mdi-pencil-outline" size="18" class="bud-header__title-icon" />
          </button>
        </h1>
        <v-text-field
          v-else
          v-model="editTitle"
          label="Title"
          variant="outlined"
          density="compact"
          autofocus
          hide-details
          class="bud-header__title-field"
          @blur="saveTitle"
          @keyup.enter="saveTitle"
          @keyup.escape="editingTitle = false"
        />

        <div class="bud-header__meta">
          <BUDAssigneeMenu :assignee-id="bud.assignee_id" @change="emit('change-assignee', $event)">
            <template #activator="{ props: menuProps }">
              <button v-bind="menuProps" type="button" class="bud-header__assignee" :aria-label="assigneeLabel">
                <span class="bud-header__avatar" :class="{ 'bud-header__avatar--empty': !bud.assignee_name }">
                  {{ bud.assignee_name ? initialsOf(bud.assignee_name) : '' }}
                </span>
                {{ bud.assignee_name || 'Unassigned' }}
              </button>
            </template>
          </BUDAssigneeMenu>
          <span>Created {{ formatDate(bud.created_at) }}</span>
          <span>Updated {{ formatDate(bud.updated_at) }}</span>
          <span v-if="bud.prod_p70_date && !isClosed">Ships by {{ formatDate(bud.prod_p70_date) }} · 70% likely</span>
        </div>
      </div>

      <div class="bud-header__actions">
        <v-btn variant="text" prepend-icon="mdi-history" title="View edit history and restore earlier versions" @click="emit('open-history')">
          History
        </v-btn>
        <v-btn
          variant="outlined"
          prepend-icon="mdi-creation-outline"
          :aria-pressed="chatOpen"
          :color="chatOpen ? 'primary' : undefined"
          :disabled="agentLocked || !chatable"
          :title="!chatable && !agentLocked ? 'Chat is not available for this section in the current stage.' : undefined"
          @click="emit('update:chatOpen', !chatOpen)"
        >
          Ask AI
        </v-btn>
        <v-btn
          v-if="nextStatus && canMoveTo(nextStatus)"
          color="primary"
          variant="flat"
          :loading="changingStatus"
          :disabled="agentLocked || changingStatus"
          @click="emit('update-status', nextStatus)"
        >
          Move to {{ BUD_STATUS_LABELS[nextStatus] }}
        </v-btn>
        <BUDMoreMenu
          :status="bud.status"
          :status-items="statusItems"
          :is-closed="isClosed"
          :agent-locked="agentLocked"
          :changing-status="changingStatus"
          :can-edit-buds="canEditBuds"
          :can-move-to="canMoveTo"
          :can-delete="canDelete"
          @update-status="emit('update-status', $event)"
          @restore="emit('restore')"
          @open-skill-settings="emit('open-skill-settings')"
          @delete="emit('delete')"
        />
      </div>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import BUDAssigneeMenu from './detail/BUDAssigneeMenu.vue'
import BUDMoreMenu from './detail/BUDMoreMenu.vue'
import BUDPriorityMenu from './detail/BUDPriorityMenu.vue'
import { BUD_STATUS_COLORS, BUD_STATUS_LABELS, budRef } from '@/types'
import type { BUDDocument, BUDPriority, BUDStatus } from '@/types'
import { initialsOf } from '@/utils/avatar'
import { formatDate } from '@/utils/date'

const props = defineProps<{
  bud: BUDDocument
  statusItems: ReadonlyArray<{ title: string; value: BUDStatus }>
  /** The stage the primary button moves to; null hides it. */
  nextStatus: BUDStatus | null
  /** Whether the viewer may move the BUD to this stage (buds:edit, or QA out of testing). */
  canMoveTo: (status: BUDStatus) => boolean
  /** A stage change is in flight. */
  changingStatus: boolean
  /** backlog:delete — gates Delete BUD. */
  canDelete: boolean
  isClosed: boolean
  agentLocked: boolean
  chatOpen: boolean
  /** False when the open section can't be chatted about at this stage (the backend would 409). */
  chatable: boolean
  canEditPriority: boolean
  /** buds:edit — gates restoring a discarded BUD. */
  canEditBuds: boolean
}>()

const emit = defineEmits<{
  'update:chatOpen': [value: boolean]
  'change-assignee': [memberId: string | null]
  'change-priority': [priority: BUDPriority]
  'update-status': [status: BUDStatus]
  restore: []
  delete: []
  'save-title': [title: string]
  'open-skill-settings': []
  'open-history': []
}>()

const assigneeLabel = computed(() =>
  `${props.bud.assignee_name ? `Assigned to ${props.bud.assignee_name}` : 'Unassigned'}. Change assignee`,
)

const editingTitle = ref(false)
const editTitle = ref('')

function startEditTitle(): void {
  if (props.agentLocked) return
  editTitle.value = props.bud.title
  editingTitle.value = true
}

function saveTitle(): void {
  const trimmed = editTitle.value.trim()
  if (trimmed && trimmed !== props.bud.title) emit('save-title', trimmed)
  editingTitle.value = false
}
</script>

<style scoped src="./detail/bud-header.css"></style>
