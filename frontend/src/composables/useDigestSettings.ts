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

/** Settings for the daily who's-out Slack post, and sending a test post. */
import { ref } from 'vue'

import api from '@/services/api'
import { extractApiError } from '@/utils/errors'

export interface DigestSettings {
  enabled: boolean
  channel_id: string
  post_time: string
  timezone: string | null
}

export interface DigestTestResult {
  ok: boolean
  error: string | null
  text: string
}

/** Plain words for Slack's error codes on a test post. */
const SLACK_ERRORS: Record<string, string> = {
  not_in_channel: 'The Bodhiorchard bot isn\'t in that channel. In Slack, type /invite @Bodhiorchard there.',
  channel_not_found: 'Slack can\'t find that channel. Check the channel ID (it starts with C or G).',
  slack_not_connected: 'Slack isn\'t connected yet. Connect it in Settings → Integrations.',
  no_channel: 'Save a channel ID first.',
}

export function testPostMessage(result: DigestTestResult): string {
  if (result.ok) return 'Posted. Check the channel.'
  return SLACK_ERRORS[result.error ?? ''] ?? `Slack refused the post (${result.error}).`
}

export function useDigestSettings() {
  const settings = ref<DigestSettings>({ enabled: false, channel_id: '', post_time: '09:30', timezone: null })
  const loading = ref(false)
  const saving = ref(false)
  const error = ref('')

  async function load(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      settings.value = (await api.get<DigestSettings>('/v1/leave/digest-settings')).data
    } catch (err) {
      error.value = extractApiError(err, "Couldn't load the daily post settings.")
    } finally {
      loading.value = false
    }
  }

  async function save(): Promise<boolean> {
    saving.value = true
    error.value = ''
    try {
      settings.value = (await api.put<DigestSettings>('/v1/leave/digest-settings', settings.value)).data
      return true
    } catch (err) {
      error.value = extractApiError(err, "Couldn't save. Check the channel ID and time.")
      return false
    } finally {
      saving.value = false
    }
  }

  async function sendTest(): Promise<string> {
    try {
      return testPostMessage((await api.post<DigestTestResult>('/v1/leave/digest/test')).data)
    } catch (err) {
      return extractApiError(err, "Couldn't send the test post.")
    }
  }

  return { settings, loading, saving, error, load, save, sendTest }
}
