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
}>()

const expanded = ref(false)
const MAX_VISIBLE_LOCATIONS = 3

const isYours = computed(
  () => !!props.currentUserId && props.todo.assigneeId === props.currentUserId,
)
const hasContext = computed(() => !!props.todo.contextMd)
const hasDescription = computed(() => !!props.todo.description)
const locations = computed(() => props.todo.codeLocations ?? [])
const visibleLocations = computed(() => locations.value.slice(0, MAX_VISIBLE_LOCATIONS))
const overflowCount = computed(() => Math.max(0, locations.value.length - MAX_VISIBLE_LOCATIONS))
const canExpand = computed(() => hasContext.value || hasDescription.value)

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
    :class="{ 'todo-row--checkpoint': todo.isCheckpoint, 'todo-row--yours': isYours }"
    @click="toggleExpanded"
  >
    <div class="todo-row__status">
      <v-icon
        v-if="todo.isCheckpoint"
        size="small"
        color="grey-darken-1"
      >mdi-gate</v-icon>
      <v-icon
        v-else
        :color="statusColor(todo.status)"
        size="small"
      >{{ statusIcon(todo.status) }}</v-icon>
    </div>

    <div class="todo-row__main">
      <div class="todo-row__title">
        <span class="todo-row__seq">#{{ todo.sequence }}</span>
        <span v-html="renderInline(todo.title)" />
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
        v-if="expanded && hasContext"
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
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06);
  cursor: default;
  transition: background-color 120ms ease;
}
.todo-row:hover {
  background-color: rgba(var(--v-theme-on-surface), 0.03);
}
.todo-row--yours {
  box-shadow: inset 3px 0 0 0 rgb(var(--v-theme-primary));
}
.todo-row--checkpoint {
  background-color: rgba(var(--v-theme-on-surface), 0.04);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: rgba(var(--v-theme-on-surface), 0.65);
}
.todo-row__status {
  padding-top: 2px;
}
.todo-row__main {
  min-width: 0;
}
.todo-row__title {
  font-size: 14.5px;
  font-weight: 500;
  line-height: 1.4;
  color: rgb(var(--v-theme-on-surface));
}
.todo-row__seq {
  display: inline-block;
  font-variant-numeric: tabular-nums;
  color: rgba(var(--v-theme-on-surface), 0.4);
  margin-right: 8px;
  font-weight: 400;
}
.todo-row__description {
  margin-top: 4px;
  font-size: 13.5px;
  color: rgba(var(--v-theme-on-surface), 0.7);
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.todo-row__description--expanded {
  -webkit-line-clamp: unset;
}
.todo-row__locations {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.todo-row__location {
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  font-size: 11.5px;
  padding: 1px 6px;
  border-radius: 3px;
  background-color: rgba(var(--v-theme-on-surface), 0.06);
  color: rgba(var(--v-theme-on-surface), 0.75);
}
.todo-row__location-more {
  font-size: 11.5px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  align-self: center;
}
.todo-row__context {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: 6px;
  background-color: rgba(var(--v-theme-on-surface), 0.04);
  font-size: 13.5px;
  line-height: 1.55;
}
.todo-row__context :deep(code) {
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  font-size: 0.9em;
  padding: 1px 4px;
  border-radius: 3px;
  background-color: rgba(var(--v-theme-on-surface), 0.08);
}
.todo-row__title :deep(code) {
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  font-size: 0.85em;
  padding: 1px 4px;
  border-radius: 3px;
  background-color: rgba(var(--v-theme-on-surface), 0.08);
}
.todo-row__repo,
.todo-row__assignee {
  display: flex;
  align-items: center;
  gap: 8px;
}
.todo-row__repo-empty {
  color: rgba(var(--v-theme-on-surface), 0.35);
  font-size: 13px;
}
</style>
