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

/**
 * Admin store for the quiz settings form and the question review/approval
 * queue. Both hit the org:edit_settings-gated backend endpoints.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

import api from '@/services/api'
import type { QuizReviewItem, QuizSettings } from '@/types/quiz'

export const useQuizReviewStore = defineStore('quizReview', () => {
  const settings = ref<QuizSettings | null>(null)
  const queue = ref<QuizReviewItem[]>([])
  const loading = ref(false)
  const saving = ref(false)
  const error = ref('')

  async function fetchSettings(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.get<QuizSettings>('/v1/settings/quiz')
      settings.value = data
    } catch {
      error.value = 'Failed to load quiz settings'
    } finally {
      loading.value = false
    }
  }

  async function saveSettings(next: QuizSettings): Promise<boolean> {
    saving.value = true
    error.value = ''
    try {
      const { data } = await api.patch<QuizSettings>('/v1/settings/quiz', next)
      settings.value = data
      return true
    } catch {
      error.value = 'Failed to save quiz settings'
      return false
    } finally {
      saving.value = false
    }
  }

  async function fetchQueue(): Promise<void> {
    loading.value = true
    try {
      const { data } = await api.get<QuizReviewItem[]>('/v1/quiz/review')
      queue.value = data
    } catch {
      error.value = 'Failed to load the review queue'
    } finally {
      loading.value = false
    }
  }

  function _replace(item: QuizReviewItem): void {
    queue.value = queue.value.map(q => (q.id === item.id ? item : q))
  }

  async function editQuestion(id: string, patch: Partial<QuizReviewItem>): Promise<boolean> {
    try {
      const { data } = await api.patch<QuizReviewItem>(`/v1/quiz/review/${id}`, patch)
      _replace(data)
      return true
    } catch {
      error.value = 'Edit rejected — check the answer matches the question'
      return false
    }
  }

  async function approve(id: string, scheduledDate?: string | null): Promise<void> {
    try {
      const { data } = await api.post<QuizReviewItem>(`/v1/quiz/review/${id}/approve`, {
        scheduledDate: scheduledDate ?? null,
      })
      _replace(data)
    } catch {
      error.value = 'Failed to approve the question'
    }
  }

  async function reject(id: string): Promise<void> {
    try {
      const { data } = await api.post<QuizReviewItem>(`/v1/quiz/review/${id}/reject`, {})
      _replace(data)
    } catch {
      error.value = 'Failed to reject the question'
    }
  }

  async function regenerate(): Promise<void> {
    try {
      await api.post('/v1/quiz/review/regenerate', {})
    } catch {
      error.value = 'Failed to request a new question'
    }
  }

  return {
    settings,
    queue,
    loading,
    saving,
    error,
    fetchSettings,
    saveSettings,
    fetchQueue,
    editQuestion,
    approve,
    reject,
    regenerate,
  }
})
