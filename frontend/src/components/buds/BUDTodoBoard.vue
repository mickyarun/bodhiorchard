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
import { onSocketReconnect } from '@/services/wsReconnect'
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
// Latest agent-stage label (set on `generating_start`, cleared on terminal).
// Bridges the 5–15 s gap between the regenerate click and the first tool_use
// event so the user sees "Agent starting…" instead of an unlabelled spinner.
const agentStageLabel = ref<string | null>(null)
// Persistent failure message — set when the agent emits `generating_failed`
// (e.g. the hard-coded 90s timeout). Surfaces in an alert until the user
// triggers another regenerate or navigates away.
const lastFailure = ref<string | null>(null)
const confirmRegenerate = ref(false)

async function reload() {
  if (props.budId) await todosStore.fetchTodos(props.budId)
}

// Live updates: refetch + flag-clear when the backend fans out events
// on the `todo:{budId}` topic.
let currentTopic: string | null = null
let currentHandler: ((data: unknown) => void) | null = null
let unregisterReconnect: (() => void) | null = null

function bindSocket(budId: string) {
  if (currentTopic && currentHandler) {
    unsubscribe(currentTopic, currentHandler)
  }
  if (unregisterReconnect) {
    unregisterReconnect()
    unregisterReconnect = null
  }
  if (!budId) {
    currentTopic = null
    currentHandler = null
    return
  }
  const topic = `todo:${budId}`
  const handler = (data: unknown) => {
    const payload = data as { event?: string; tool?: string; error?: string } | null
    const event = payload?.event
    if (event === 'generating_start') {
      agentStageLabel.value = 'Starting…'
      lastFailure.value = null
      return
    }
    if (event === 'generating_tool_use') {
      agentStageLabel.value = null
      lastTool.value = payload?.tool ?? null
      return
    }
    if (event === 'generating_failed') {
      lastTool.value = null
      agentStageLabel.value = null
      lastFailure.value = payload?.error ?? 'Agent failed without a message'
      // Belt-and-suspenders: a failure event MUST clear the regenerate
      // spinner. `handleRemoteEvent` does this too, but it gates on
      // `currentBudId.value === budId`, which a navigation race can
      // miss. Flipping the flag here unconditionally guarantees the
      // spinner hides whenever a failure is surfaced in this panel.
      todosStore.regenerating = false
    }
    if (event === 'todos_regenerated') {
      lastTool.value = null
      agentStageLabel.value = null
      lastFailure.value = null
    }
    void todosStore.handleRemoteEvent(budId, event)
  }
  subscribe(topic, handler)
  currentTopic = topic
  currentHandler = handler

  // Refetch on every WS reconnect — events fired while the socket was
  // dropped (backend restart, network blip) are not buffered, so a
  // `todos_regenerated` or `generating_failed` issued during the gap
  // would leave the board stale + the regenerating spinner stuck.
  // Pulling fresh todos resyncs both the row list and the regenerating
  // flag (cleared inside `handleRemoteEvent` on terminal events).
  unregisterReconnect = onSocketReconnect(() => todosStore.fetchTodos(budId))
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
  if (unregisterReconnect) {
    unregisterReconnect()
    unregisterReconnect = null
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
        <span
          v-else-if="todosStore.regenerating && agentStageLabel"
          class="todo-board__tool-hint"
        >Agent {{ agentStageLabel.toLowerCase() }}</span>
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

    <v-alert
      v-if="lastFailure"
      type="error"
      variant="tonal"
      class="ma-3"
      closable
      @click:close="lastFailure = null"
    >{{ lastFailure }}</v-alert>

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
    >No TODOs yet — click Regenerate to re-derive them from the current tech spec.</div>

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
          TODOs will be re-derived from the current tech spec.
          In-flight TODOs (claimed, in-progress, or completed) are preserved.
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
