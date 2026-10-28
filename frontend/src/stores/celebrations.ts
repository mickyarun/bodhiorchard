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
 * Admin store for the celebrations settings form, the sample post, the
 * audience count and the Slack profile-photo import. Every endpoint it
 * calls sits behind `employees:manage` on the backend.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

import api from '@/services/api'
import type {
  CelebrationAudience,
  CelebrationPostHistory,
  CelebrationSettings,
  CelebrationTestResult,
} from '@/types/celebrations'
import { extractApiError } from '@/utils/errors'

export const useCelebrationsStore = defineStore('celebrations', () => {
  const settings = ref<CelebrationSettings | null>(null)
  const audience = ref<CelebrationAudience | null>(null)
  const history = ref<CelebrationPostHistory[]>([])
  const loading = ref(false)
  const saving = ref(false)
  const testing = ref(false)
  const error = ref('')

  async function fetchSettings(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.get<CelebrationSettings>('/v1/settings/celebrations')
      settings.value = data
    } catch (err) {
      error.value = extractApiError(err, 'Failed to load celebration settings')
    } finally {
      loading.value = false
    }
  }

  async function saveSettings(next: CelebrationSettings): Promise<boolean> {
    saving.value = true
    error.value = ''
    try {
      const { data } = await api.patch<CelebrationSettings>(
        '/v1/settings/celebrations',
        next
      )
      settings.value = data
      return true
    } catch (err) {
      // The backend rejects "enabled with no channel" and "enabled with
      // neither stream" — surface its message rather than a generic one.
      error.value = extractApiError(err, 'Failed to save celebration settings')
      return false
    } finally {
      saving.value = false
    }
  }

  /** The last two weeks of digests and how each went (sent, failed …). */
  async function fetchHistory(): Promise<void> {
    try {
      const { data } = await api.get<CelebrationPostHistory[]>(
        '/v1/settings/celebrations/history'
      )
      history.value = data
    } catch {
      // Informational only; the form works without it.
      history.value = []
    }
  }

  /** Counts of people who will be announced — shown before switching on. */
  async function fetchAudience(): Promise<void> {
    try {
      const { data } = await api.get<CelebrationAudience>(
        '/v1/settings/celebrations/audience'
      )
      audience.value = data
    } catch {
      // Informational only; the form works without it.
      audience.value = null
    }
  }

  /**
   * Post a labelled sample with the caller as the celebrant. Never touches
   * the real schedule, so it is safe on any day and safe to repeat. Sends
   * the unsaved form so a channel can be checked before it is saved.
   */
  async function sendTest(form: CelebrationSettings): Promise<CelebrationTestResult | null> {
    testing.value = true
    error.value = ''
    try {
      const { data } = await api.post<CelebrationTestResult>(
        '/v1/settings/celebrations/test',
        form
      )
      return data
    } catch (err) {
      error.value = extractApiError(err, 'Failed to send the test post')
      return null
    } finally {
      testing.value = false
    }
  }

  return {
    settings,
    audience,
    history,
    loading,
    saving,
    testing,
    error,
    fetchSettings,
    fetchAudience,
    fetchHistory,
    saveSettings,
    sendTest,
  }
})
