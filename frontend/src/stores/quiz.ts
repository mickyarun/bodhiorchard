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
 * Player-facing quiz store — today's quiz, answer submission, reveal, and the
 * monthly/daily leaderboards. Pure engagement: NO XP is ever awarded (the only
 * reward is a rare monthly SP grant handled entirely server-side).
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

import api from '@/services/api'
import type {
  QuizActive,
  QuizAnswerResult,
  QuizLeaderboardEntry,
  QuizRecap,
  QuizResponse,
  QuizReveal,
} from '@/types/quiz'

export const useQuizStore = defineStore('quiz', () => {
  const active = ref<QuizActive | null>(null)
  const reveal = ref<QuizReveal | null>(null)
  const monthly = ref<QuizLeaderboardEntry[]>([])
  const recap = ref<QuizRecap | null>(null)
  const loading = ref(false)
  const submitting = ref(false)
  const error = ref('')

  async function fetchActive(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.get<QuizActive | null>('/v1/quiz/active')
      active.value = data
    } catch {
      error.value = 'Failed to load the quiz'
    } finally {
      loading.value = false
    }
  }

  async function submitAnswer(quizId: string, response: QuizResponse): Promise<boolean> {
    submitting.value = true
    error.value = ''
    try {
      const { data } = await api.post<QuizAnswerResult>(`/v1/quiz/${quizId}/answers`, {
        response,
      })
      if (active.value) active.value = { ...active.value, alreadyAnswered: true }
      return data.accepted
    } catch {
      error.value = 'Could not submit your answer'
      return false
    } finally {
      submitting.value = false
    }
  }

  async function fetchReveal(quizId: string): Promise<void> {
    try {
      const { data } = await api.get<QuizReveal>(`/v1/quiz/${quizId}/reveal`)
      reveal.value = data
    } catch {
      // Reveal not available yet (403 before window close) — leave null.
      reveal.value = null
    }
  }

  async function fetchMonthly(month?: string): Promise<void> {
    try {
      const { data } = await api.get<QuizLeaderboardEntry[]>('/v1/quiz/leaderboard', {
        params: month ? { month } : undefined,
      })
      monthly.value = data
    } catch {
      error.value = 'Failed to load the leaderboard'
    }
  }

  async function fetchRecap(month?: string): Promise<void> {
    try {
      const { data } = await api.get<QuizRecap>('/v1/quiz/recap', {
        params: month ? { month } : undefined,
      })
      recap.value = data
    } catch {
      error.value = 'Failed to load past quizzes'
    }
  }

  return {
    active,
    reveal,
    monthly,
    recap,
    loading,
    submitting,
    error,
    fetchActive,
    submitAnswer,
    fetchReveal,
    fetchMonthly,
    fetchRecap,
  }
})
