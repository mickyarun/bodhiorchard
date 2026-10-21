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

/** Slack status on WFH and leave days: HR's app settings and each member's own connection. */
import { ref } from 'vue'

import api from '@/services/api'
import { extractApiError } from '@/utils/errors'

export interface SlackStatusSettings {
  enabled: boolean
  client_id: string
  has_client_secret: boolean
  redirect_url: string
}

export interface SlackStatusMine {
  available: boolean
  connected: boolean
}

/** What happened when Slack sent the member back (?slackStatus=…). */
const OUTCOMES: Record<string, { ok: boolean; text: string }> = {
  connected: { ok: true, text: 'Connected. Your Slack status will show WFH and leave days.' },
  cancelled: { ok: false, text: 'You cancelled in Slack, so nothing changed.' },
  expired: { ok: false, text: 'That link expired. Try connecting again.' },
  wrong_account: {
    ok: false,
    text: "That wasn't the Slack account linked to you here. Sign in to your own Slack account and try again.",
  },
  rotation: {
    ok: false,
    text: "The Slack app has token rotation turned on, which this doesn't support. Ask HR to turn it off in the app's OAuth settings.",
  },
  failed: { ok: false, text: "Slack didn't finish connecting. Try again, or ask HR to check the Slack app settings." },
}

export function connectOutcome(code: string | null | undefined): { ok: boolean; text: string } | null {
  return code ? (OUTCOMES[code] ?? OUTCOMES.failed) : null
}

/** HR: the Slack app's OAuth client. */
export function useSlackStatusSettings() {
  const settings = ref<SlackStatusSettings>({
    enabled: false,
    client_id: '',
    has_client_secret: false,
    redirect_url: '',
  })
  const saving = ref(false)
  const error = ref('')

  async function load(): Promise<void> {
    try {
      settings.value = (await api.get<SlackStatusSettings>('/v1/leave/slack-status')).data
    } catch (err) {
      error.value = extractApiError(err, "Couldn't load the Slack status settings.")
    }
  }

  /** Save; ``secret`` null keeps the saved one. */
  async function save(secret: string | null): Promise<boolean> {
    saving.value = true
    error.value = ''
    try {
      const { enabled, client_id } = settings.value
      const body = { enabled, client_id, client_secret: secret }
      settings.value = (await api.put<SlackStatusSettings>('/v1/leave/slack-status', body)).data
      return true
    } catch (err) {
      error.value = extractApiError(err, "Couldn't save. Check the client ID.")
      return false
    } finally {
      saving.value = false
    }
  }

  return { settings, saving, error, load, save }
}

/** A member: offered here? connected? and connecting / disconnecting. */
export function useMySlackStatus() {
  const mine = ref<SlackStatusMine | null>(null)
  const busy = ref(false)
  const error = ref('')

  async function load(): Promise<void> {
    try {
      mine.value = (await api.get<SlackStatusMine>('/v1/leave/slack-status/me')).data
    } catch {
      mine.value = null // Optional feature: say nothing rather than an error banner.
    }
  }

  async function connect(): Promise<void> {
    busy.value = true
    error.value = ''
    try {
      const { url } = (await api.post<{ url: string }>('/v1/leave/slack-status/me/connect')).data
      window.location.assign(url)
    } catch (err) {
      error.value = extractApiError(err, "Couldn't start connecting to Slack.")
      busy.value = false
    }
  }

  async function disconnect(): Promise<void> {
    busy.value = true
    error.value = ''
    try {
      await api.delete('/v1/leave/slack-status/me')
      if (mine.value) mine.value = { ...mine.value, connected: false }
    } catch (err) {
      error.value = extractApiError(err, "Couldn't turn it off. Try again.")
    } finally {
      busy.value = false
    }
  }

  return { mine, busy, error, load, connect, disconnect }
}
