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
   */
  async function handleRemoteEvent(budId: string): Promise<void> {
    if (currentBudId.value === budId) {
      await fetchTodos(budId)
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
  }

  return {
    todos,
    loading,
    error,
    currentBudId,
    fetchTodos,
    claimTodo,
    updateTodo,
    handleRemoteEvent,
    reset,
  }
})
