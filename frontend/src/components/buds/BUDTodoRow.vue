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
import { computed, ref } from 'vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import type { BUDTodo, BUDTodoStatus } from '@/types'

const props = defineProps<{
  todo: BUDTodo
  currentUserId: string | null
  busy: boolean
}>()

const emit = defineEmits<{
  claim: [todo: BUDTodo]
  status: [todo: BUDTodo, status: BUDTodoStatus]
  edit: [todo: BUDTodo, title: string]
}>()

const expanded = ref(false)
const MAX_VISIBLE_LOCATIONS = 3

// Inline title edit. Checkpoints are review gates, not editable tasks.
const canEditTitle = computed(() => !props.todo.isCheckpoint)
const editingTitle = ref(false)
const editTitle = ref('')

function startEditTitle(): void {
  if (!canEditTitle.value || props.busy) return
  editTitle.value = props.todo.title
  editingTitle.value = true
}

function saveTitle(): void {
  const trimmed = editTitle.value.trim()
  if (trimmed && trimmed !== props.todo.title) {
    emit('edit', props.todo, trimmed)
  }
  editingTitle.value = false
}

const isYours = computed(
  () => !!props.currentUserId && props.todo.assigneeId === props.currentUserId,
)
const hasContext = computed(() => !!props.todo.contextMd)
const hasDescription = computed(() => !!props.todo.description)
const locations = computed(() => props.todo.codeLocations ?? [])
const visibleLocations = computed(() => locations.value.slice(0, MAX_VISIBLE_LOCATIONS))
const overflowCount = computed(() => Math.max(0, locations.value.length - MAX_VISIBLE_LOCATIONS))
// context_md is always shown; only description still needs click-to-expand
const canExpand = computed(() => hasDescription.value)

function renderInline(md: string): string {
  return DOMPurify.sanitize(marked.parseInline(md, { async: false }) as string)
}

function renderBlock(md: string): string {
  return DOMPurify.sanitize(marked.parse(md, { async: false }) as string)
}

function statusColor(s: string): string {
  if (s === 'completed') return 'success'
  if (s === 'in_progress') return 'primary'
  if (s === 'blocked') return 'error'
  return 'grey'
}

function statusIcon(s: string): string {
  if (s === 'completed') return 'mdi-check-circle'
  if (s === 'in_progress') return 'mdi-progress-clock'
  if (s === 'blocked') return 'mdi-alert-circle'
  return 'mdi-circle-outline'
}

function toggleExpanded() {
  if (canExpand.value) expanded.value = !expanded.value
}
</script>

<template>
  <div
    class="todo-row"
    :class="{
      'todo-row--checkpoint': todo.isCheckpoint,
      'todo-row--yours': isYours,
      'todo-row--expandable': canExpand,
    }"
    @click="toggleExpanded"
  >
    <div class="todo-row__status">
      <v-icon
        v-if="todo.isCheckpoint"
        size="small"
        color="primary"
      >mdi-shield-check-outline</v-icon>
      <v-icon
        v-else
        :color="statusColor(todo.status)"
        size="small"
      >{{ statusIcon(todo.status) }}</v-icon>
    </div>

    <div class="todo-row__main">
      <div class="todo-row__title">
        <span class="todo-row__seq">#{{ todo.sequence }}</span>
        <v-text-field
          v-if="editingTitle"
          v-model="editTitle"
          variant="outlined"
          density="compact"
          autofocus
          hide-details
          class="todo-row__title-input"
          @click.stop
          @blur="saveTitle"
          @keyup.enter="saveTitle"
          @keyup.escape="editingTitle = false"
        />
        <template v-else>
          <span v-html="renderInline(todo.title)" />
          <v-chip
            v-if="todo.isCheckpoint"
            size="x-small"
            color="primary"
            variant="tonal"
            class="todo-row__review-badge"
          >review</v-chip>
          <v-btn
            v-if="canEditTitle"
            icon="mdi-pencil-outline"
            size="x-small"
            variant="text"
            density="compact"
            class="todo-row__edit-btn"
            :disabled="busy"
            title="Edit text"
            @click.stop="startEditTitle"
          />
        </template>
      </div>
      <div
        v-if="hasDescription"
        class="todo-row__description"
        :class="{ 'todo-row__description--expanded': expanded }"
      >
        {{ todo.description }}
      </div>
      <div v-if="locations.length" class="todo-row__locations">
        <code
          v-for="loc in visibleLocations"
          :key="loc"
          class="todo-row__location"
        >{{ loc }}</code>
        <span v-if="overflowCount > 0" class="todo-row__location-more">
          +{{ overflowCount }} more
        </span>
      </div>
      <div
        v-if="hasContext"
        class="todo-row__context"
        v-html="renderBlock(todo.contextMd!)"
      />
    </div>

    <div class="todo-row__repo">
      <v-chip
        v-if="todo.repoName"
        size="x-small"
        variant="tonal"
        @click.stop
      >{{ todo.repoName }}</v-chip>
      <span v-else class="todo-row__repo-empty">—</span>
    </div>

    <div class="todo-row__assignee" @click.stop>
      <v-chip v-if="todo.assigneeName" size="x-small" variant="tonal">
        {{ todo.assigneeName }}
      </v-chip>
      <v-btn
        v-else-if="!todo.isCheckpoint && todo.status !== 'completed'"
        size="x-small"
        variant="text"
        :disabled="busy"
        @click="emit('claim', todo)"
      >Claim</v-btn>
      <span v-else class="todo-row__repo-empty">—</span>

      <v-btn
        v-if="isYours && todo.status === 'pending'"
        size="x-small"
        variant="text"
        color="primary"
        :disabled="busy"
        @click="emit('status', todo, 'in_progress')"
      >Start</v-btn>
      <v-btn
        v-if="isYours && todo.status === 'in_progress'"
        size="x-small"
        variant="text"
        color="success"
        :disabled="busy"
        @click="emit('status', todo, 'completed')"
      >Done</v-btn>
    </div>
  </div>
</template>

<style scoped>
.todo-row {
  display: grid;
  grid-template-columns: 32px 1fr auto auto;
  align-items: start;
  gap: 12px;
  padding: 14px 20px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06);
  cursor: default;
  transition: background-color 120ms ease;
}
.todo-row--expandable { cursor: pointer; }
.todo-row--expandable:hover { background-color: rgba(var(--v-theme-on-surface), 0.03); }
.todo-row--yours { box-shadow: inset 3px 0 0 0 rgb(var(--v-theme-primary)); }
.todo-row--checkpoint {
  background-color: rgba(var(--v-theme-primary), 0.05);
  box-shadow: inset 3px 0 0 0 rgba(var(--v-theme-primary), 0.5);
}
.todo-row--checkpoint .todo-row__title { color: rgb(var(--v-theme-primary)); font-weight: 600; }
.todo-row--checkpoint .todo-row__seq   { color: rgba(var(--v-theme-primary), 0.55); }
.todo-row__status { padding-top: 3px; }
.todo-row__main   { min-width: 0; }

.todo-row__title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 14.5px;
  font-weight: 500;
  line-height: 1.4;
  color: rgb(var(--v-theme-on-surface));
}
.todo-row__seq {
  font-variant-numeric: tabular-nums;
  color: rgba(var(--v-theme-on-surface), 0.38);
  font-weight: 400;
  font-size: 13px;
  flex-shrink: 0;
}
.todo-row__review-badge { margin-left: 2px; }
.todo-row__title-input { min-width: 260px; max-width: 520px; }
/* Pencil stays quiet until the row is hovered, so it doesn't compete with
   the title text — same restraint as the BUD-title edit affordance. */
.todo-row__edit-btn { opacity: 0; transition: opacity 120ms ease; }
.todo-row:hover .todo-row__edit-btn { opacity: 0.55; }
.todo-row__edit-btn:hover { opacity: 1; }
.todo-row__description {
  margin-top: 4px;
  font-size: 13.5px;
  color: rgba(var(--v-theme-on-surface), 0.65);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.todo-row__description--expanded { -webkit-line-clamp: unset; }
.todo-row__locations {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.todo-row__location {
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 4px;
  background-color: rgba(var(--v-theme-on-surface), 0.07);
  color: rgba(var(--v-theme-on-surface), 0.7);
  border: 1px solid rgba(var(--v-theme-on-surface), 0.07);
}
.todo-row__location-more {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.45);
  align-self: center;
}

/*
 * Left-border accent (not a box) — context flows from the row
 * rather than feeling like a detached card.
 */
.todo-row__context {
  margin-top: 12px;
  padding-left: 14px;
  border-left: 2px solid rgba(var(--v-theme-on-surface), 0.14);
  font-size: 13px;
  line-height: 1.65;
  color: rgba(var(--v-theme-on-surface), 0.75);
}
.todo-row__context :deep(ul),
.todo-row__context :deep(ol)          { margin: 0; padding-left: 18px; }
.todo-row__context :deep(li)          { margin-top: 5px; }
.todo-row__context :deep(li:first-child) { margin-top: 0; }
.todo-row__context :deep(p)           { margin: 0 0 6px; }
/* Shared monospace token for inline code in context and title */
.todo-row__context :deep(code),
.todo-row__title   :deep(code) {
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  padding: 1px 5px;
  border-radius: 3px;
  background-color: rgba(var(--v-theme-on-surface), 0.09);
}
.todo-row__context :deep(code) { font-size: 0.88em; color: rgba(var(--v-theme-on-surface), 0.9); }
.todo-row__title   :deep(code) { font-size: 0.82em; }
.todo-row__repo,
.todo-row__assignee { display: flex; align-items: center; gap: 8px; padding-top: 2px; }
.todo-row__repo-empty { color: rgba(var(--v-theme-on-surface), 0.3); font-size: 13px; }
</style>
