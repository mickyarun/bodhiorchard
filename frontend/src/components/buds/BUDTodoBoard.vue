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
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useBUDTodosStore } from '@/stores/bud_todos'
import { useAuthStore } from '@/stores/auth'
import { subscribe, unsubscribe } from '@/services/socket'
import BUDTodoRow from './BUDTodoRow.vue'
import type { BUDTodo, BUDTodoStatus } from '@/types'

const props = defineProps<{ budId: string }>()

const todosStore = useBUDTodosStore()
const authStore = useAuthStore()

const currentUserId = computed(() => authStore.user?.id ?? null)

const progress = computed(() => {
  const items = todosStore.todos.filter(t => !t.isCheckpoint)
  const done = items.filter(t => t.status === 'completed').length
  return {
    done,
    total: items.length,
    pct: items.length ? Math.round((done / items.length) * 100) : 0,
  }
})

// Last `generating_tool_use` event — surfaced as a hint while regenerating.
const lastTool = ref<string | null>(null)
const confirmRegenerate = ref(false)

async function reload() {
  if (props.budId) await todosStore.fetchTodos(props.budId)
}

// Live updates: refetch + flag-clear when the backend fans out events
// on the `todo:{budId}` topic.
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
  const handler = (data: unknown) => {
    const event = (data as { event?: string } | null)?.event
    if (event === 'generating_tool_use') {
      lastTool.value = (data as { tool?: string }).tool ?? null
      return
    }
    if (event === 'todos_regenerated' || event === 'generating_failed') {
      lastTool.value = null
    }
    void todosStore.handleRemoteEvent(budId, event)
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
  await todosStore.claimTodo(props.budId, todo.id)
}

async function handleStatus(todo: BUDTodo, status: BUDTodoStatus) {
  await todosStore.updateTodo(props.budId, todo.id, { status })
}

function openRegenerateConfirm() {
  confirmRegenerate.value = true
}

async function doRegenerate() {
  confirmRegenerate.value = false
  await todosStore.regenerate(props.budId)
}
</script>

<template>
  <v-card variant="outlined" class="mb-4">
    <div class="todo-board__header">
      <div class="todo-board__title">
        <v-icon size="small" class="mr-2">mdi-format-list-checks</v-icon>
        <span>Implementation TODOs</span>
        <v-chip v-if="progress.total" size="x-small" class="ml-3">
          {{ progress.done }}/{{ progress.total }} done
        </v-chip>
      </div>
      <div class="todo-board__actions">
        <span
          v-if="todosStore.regenerating && lastTool"
          class="todo-board__tool-hint"
        >Agent using {{ lastTool }}…</span>
        <v-btn
          size="small"
          variant="text"
          :loading="todosStore.regenerating"
          :disabled="todosStore.regenerating || !todosStore.todos.length && todosStore.loading"
          prepend-icon="mdi-refresh"
          @click="openRegenerateConfirm"
        >Regenerate</v-btn>
      </div>
    </div>

    <v-progress-linear
      v-if="progress.total"
      :model-value="progress.pct"
      color="success"
      height="3"
    />
    <v-progress-linear
      v-else-if="todosStore.regenerating"
      indeterminate
      color="primary"
      height="3"
    />

    <div
      v-if="todosStore.loading && todosStore.todos.length === 0"
      class="pa-4 text-center"
    >
      <v-progress-circular indeterminate size="24" />
    </div>

    <v-alert
      v-else-if="todosStore.error"
      type="error"
      variant="tonal"
      class="ma-3"
    >{{ todosStore.error }}</v-alert>

    <div
      v-else-if="todosStore.todos.length === 0"
      class="pa-4 text-center text-medium-emphasis"
    >No TODOs yet — click Regenerate to run the todo-generator agent.</div>

    <div v-else class="todo-board__list">
      <BUDTodoRow
        v-for="todo in todosStore.todos"
        :key="todo.id"
        :todo="todo"
        :current-user-id="currentUserId"
        :busy="todosStore.loading || todosStore.regenerating"
        @claim="handleClaim"
        @status="handleStatus"
      />
    </div>

    <v-dialog v-model="confirmRegenerate" max-width="420">
      <v-card>
        <v-card-title class="text-h6">Regenerate TODOs?</v-card-title>
        <v-card-text class="text-body-2">
          The todo-generator agent will re-split the tech spec.
          In-flight TODOs (claimed, in-progress, or completed) are preserved.
          This takes 30–120 seconds.
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="confirmRegenerate = false">Cancel</v-btn>
          <v-btn color="primary" variant="flat" @click="doRegenerate">Regenerate</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<style scoped>
.todo-board__header {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  gap: 12px;
}
.todo-board__title {
  display: flex;
  align-items: center;
  font-size: 15px;
  font-weight: 500;
}
.todo-board__actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
}
.todo-board__tool-hint {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-style: italic;
}
.todo-board__list {
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}
</style>
