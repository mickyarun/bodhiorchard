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
import { computed, onMounted, onUnmounted, watch } from 'vue'
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { useBUDTodosStore } from '@/stores/bud_todos'
import { useAuthStore } from '@/stores/auth'
import { subscribe, unsubscribe } from '@/services/socket'
import type { BUDTodo } from '@/types'

// Titles come from the tech-spec parser as inline markdown
// (``**[Module]** Verb …`` / `` `code` ``). Render inline so we don't
// wrap each title in `<p>` tags.
function renderInlineTitle(md: string): string {
  if (!md) return ''
  return DOMPurify.sanitize(marked.parseInline(md, { async: false }) as string)
}

const props = defineProps<{ budId: string }>()

const todosStore = useBUDTodosStore()
const authStore = useAuthStore()

const currentUserId = computed(() => authStore.user?.id ?? null)

const progress = computed(() => {
  const implItems = todosStore.todos.filter(t => !t.isCheckpoint)
  const done = implItems.filter(t => t.status === 'completed').length
  return {
    done,
    total: implItems.length,
    pct: implItems.length ? Math.round((done / implItems.length) * 100) : 0,
  }
})

async function reload() {
  if (props.budId) await todosStore.fetchTodos(props.budId)
}

// Live updates: refetch when the backend fans out `todo:{budId}` events
// (claim, cascade from a top-level reassignment, future status pushes).
let currentTopic: string | null = null
let currentHandler: ((data: unknown) => void) | null = null

function bindSocket(budId: string) {
  if (currentTopic && currentHandler) {
    unsubscribe(currentTopic, currentHandler)
  }
  if (!budId) {
    currentTopic = null
    currentHandler = null
    return
  }
  const topic = `todo:${budId}`
  const handler = () => {
    void todosStore.handleRemoteEvent(budId)
  }
  subscribe(topic, handler)
  currentTopic = topic
  currentHandler = handler
}

onMounted(() => {
  void reload()
  bindSocket(props.budId)
})
watch(
  () => props.budId,
  (id) => {
    void reload()
    bindSocket(id)
  },
)
onUnmounted(() => {
  if (currentTopic && currentHandler) {
    unsubscribe(currentTopic, currentHandler)
  }
  todosStore.reset()
})

async function handleClaim(todo: BUDTodo) {
  if (todo.isCheckpoint) return
  await todosStore.claimTodo(props.budId, todo.id)
}

async function markInProgress(todo: BUDTodo) {
  await todosStore.updateTodo(props.budId, todo.id, { status: 'in_progress' })
}

async function markCompleted(todo: BUDTodo) {
  await todosStore.updateTodo(props.budId, todo.id, { status: 'completed' })
}

function statusColor(status: string): string {
  switch (status) {
    case 'completed': return 'success'
    case 'in_progress': return 'primary'
    case 'blocked': return 'error'
    default: return 'grey'
  }
}

function statusIcon(status: string): string {
  switch (status) {
    case 'completed': return 'mdi-check-circle'
    case 'in_progress': return 'mdi-progress-clock'
    case 'blocked': return 'mdi-alert-circle'
    default: return 'mdi-circle-outline'
  }
}

function isYours(todo: BUDTodo): boolean {
  return !!currentUserId.value && todo.assigneeId === currentUserId.value
}
</script>

<template>
  <v-card variant="outlined" class="mb-4">
    <v-card-title class="d-flex align-center">
      <v-icon size="small" class="mr-2">mdi-format-list-checks</v-icon>
      Implementation TODOs
      <v-spacer />
      <v-chip v-if="progress.total" size="small">
        {{ progress.done }}/{{ progress.total }} done
      </v-chip>
    </v-card-title>

    <v-progress-linear
      v-if="progress.total"
      :model-value="progress.pct"
      color="success"
      height="4"
    />

    <div v-if="todosStore.loading && todosStore.todos.length === 0" class="pa-4 text-center">
      <v-progress-circular indeterminate size="24" />
    </div>

    <v-alert
      v-else-if="todosStore.error"
      type="error"
      variant="tonal"
      class="ma-3"
    >
      {{ todosStore.error }}
    </v-alert>

    <div v-else-if="todosStore.todos.length === 0" class="pa-4 text-center text-medium-emphasis">
      No TODOs parsed from the tech spec yet.
    </div>

    <v-list v-else density="comfortable">
      <template v-for="todo in todosStore.todos" :key="todo.id">
        <!-- Checkpoint row: divider-style -->
        <v-list-item
          v-if="todo.isCheckpoint"
          class="bg-grey-lighten-4 text-caption text-uppercase"
        >
          <template #prepend>
            <v-icon size="x-small" color="grey-darken-1">mdi-gate</v-icon>
          </template>
          <v-list-item-title class="todo-title font-weight-medium">
            <span v-html="renderInlineTitle(todo.title)" />
          </v-list-item-title>
        </v-list-item>

        <!-- Regular TODO row -->
        <v-list-item
          v-else
          :class="{ 'todo-yours': isYours(todo) }"
        >
          <template #prepend>
            <v-icon :color="statusColor(todo.status)">{{ statusIcon(todo.status) }}</v-icon>
          </template>

          <v-list-item-title class="todo-title">
            <span class="text-caption text-medium-emphasis mr-2">#{{ todo.sequence }}</span>
            <span v-html="renderInlineTitle(todo.title)" />
          </v-list-item-title>

          <v-list-item-subtitle v-if="todo.summary" class="mt-1 text-body-2">
            {{ todo.summary }}
          </v-list-item-subtitle>

          <template #append>
            <div class="d-flex align-center ga-2">
              <v-chip v-if="todo.assigneeName" size="x-small" variant="tonal">
                {{ todo.assigneeName }}
              </v-chip>
              <v-chip v-else size="x-small" variant="outlined" color="grey">
                unassigned
              </v-chip>

              <v-btn
                v-if="!isYours(todo) && todo.status !== 'completed'"
                size="x-small"
                variant="text"
                :disabled="todosStore.loading"
                @click="handleClaim(todo)"
              >
                Claim
              </v-btn>

              <v-btn
                v-if="isYours(todo) && todo.status === 'pending'"
                size="x-small"
                variant="text"
                color="primary"
                :disabled="todosStore.loading"
                @click="markInProgress(todo)"
              >
                Start
              </v-btn>

              <v-btn
                v-if="isYours(todo) && todo.status === 'in_progress'"
                size="x-small"
                variant="text"
                color="success"
                :disabled="todosStore.loading"
                @click="markCompleted(todo)"
              >
                Done
              </v-btn>
            </div>
          </template>
        </v-list-item>
      </template>
    </v-list>
  </v-card>
</template>

<style scoped>
.todo-yours {
  border-left: 3px solid rgb(var(--v-theme-primary));
}

/* Vuetify's v-list-item-title defaults to single-line ellipsis truncation,
   which mangles long todo titles. Allow wrap so the full title is readable. */
.todo-title {
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
  line-height: 1.4;
}

/* Inline code spans inside rendered markdown — match Vuetify's monospace feel. */
.todo-title :deep(code) {
  font-family: 'SF Mono', Menlo, Consolas, monospace;
  font-size: 0.85em;
  padding: 1px 4px;
  border-radius: 3px;
  background-color: rgba(var(--v-theme-on-surface), 0.08);
}
</style>
