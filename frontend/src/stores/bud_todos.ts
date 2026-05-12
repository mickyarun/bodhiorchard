// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/services/api'
import type { BUDTodo, BUDTodoStatus } from '@/types'
import { extractApiError } from '@/utils/errors'

/**
 * Store for BUD TODO board — discrete work items parsed from a BUD's
 * tech spec. Supports claim (self-assign), update (status/assignee),
 * and auto-assign (smart distribute).
 *
 * Live updates arrive via the `todo:{budId}` WebSocket topic when
 * another developer takes over or completes a TODO.
 */
export const useBUDTodosStore = defineStore('budTodos', () => {
  const todos = ref<BUDTodo[]>([])
  const loading = ref(false)
  const error = ref('')
  const currentBudId = ref<string | null>(null)
  // True between POST /todos/regenerate and the bg task's terminal event
  // (todos_regenerated | generating_failed) — drives the button spinner.
  const regenerating = ref(false)

  async function fetchTodos(budId: string): Promise<void> {
    loading.value = true
    error.value = ''
    currentBudId.value = budId
    try {
      const { data } = await api.get(`/v1/buds/${budId}/todos`)
      todos.value = data as BUDTodo[]
    } catch (e: unknown) {
      error.value = extractApiError(e, 'Failed to load TODOs')
      todos.value = []
    } finally {
      loading.value = false
    }
  }

  async function claimTodo(budId: string, todoId: string): Promise<BUDTodo | null> {
    try {
      const { data } = await api.post(`/v1/buds/${budId}/todos/${todoId}/claim`)
      _applyLocalUpdate(data.todo)
      return data.todo as BUDTodo
    } catch (e: unknown) {
      error.value = extractApiError(e, 'Failed to claim TODO')
      return null
    }
  }

  async function updateTodo(
    budId: string,
    todoId: string,
    patch: { status?: BUDTodoStatus; assigneeId?: string | null; summary?: string },
  ): Promise<BUDTodo | null> {
    try {
      const { data } = await api.patch(`/v1/buds/${budId}/todos/${todoId}`, patch)
      _applyLocalUpdate(data as BUDTodo)
      return data as BUDTodo
    } catch (e: unknown) {
      error.value = extractApiError(e, 'Failed to update TODO')
      return null
    }
  }

  /**
   * Called by the WebSocket handler when a `todo:{budId}` event arrives.
   * Refreshes the specific TODO that changed. We refetch the whole list
   * for simplicity — list size is small (typically 5-15 TODOs).
   *
   * Also clears the `regenerating` flag on terminal regenerate events
   * (`todos_regenerated` / `generating_failed`) so the UI spinner stops
   * even if the user navigated away and back.
   */
  async function handleRemoteEvent(
    budId: string,
    event?: string,
  ): Promise<void> {
    if (currentBudId.value !== budId) return
    if (event === 'todos_regenerated' || event === 'generating_failed') {
      regenerating.value = false
    }
    await fetchTodos(budId)
  }

  /**
   * Trigger an async regenerate of all TODOs via the `todo-generator`
   * agent. Returns 202 immediately; the WS topic carries the progress
   * events. In-flight TODOs (claimed / in-progress / completed) are
   * always preserved.
   *
   * On 409 (`already running`) we leave `regenerating` true — the
   * existing task will fire the terminal event that clears it.
   */
  async function regenerate(budId: string): Promise<void> {
    regenerating.value = true
    try {
      await api.post(`/v1/buds/${budId}/todos/regenerate`)
    } catch (e: unknown) {
      const msg = extractApiError(e, 'Failed to start regenerate')
      // 409 = already running; let the existing task complete.
      if (!msg.toLowerCase().includes('already')) {
        regenerating.value = false
        error.value = msg
      }
    }
  }

  function _applyLocalUpdate(updated: BUDTodo): void {
    const idx = todos.value.findIndex(t => t.id === updated.id)
    if (idx >= 0) todos.value[idx] = updated
  }

  function reset(): void {
    todos.value = []
    currentBudId.value = null
    error.value = ''
    regenerating.value = false
  }

  return {
    todos,
    loading,
    error,
    regenerating,
    currentBudId,
    fetchTodos,
    claimTodo,
    updateTodo,
    regenerate,
    handleRemoteEvent,
    reset,
  }
})
