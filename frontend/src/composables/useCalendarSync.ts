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

/** Google Calendar sync settings for leave and WFH, and checking they work. */
import { ref } from 'vue'

import api from '@/services/api'
import { extractApiError } from '@/utils/errors'

export interface CalendarSyncSettings {
  enabled: boolean
  decline_meetings: boolean
  decline_message: string
  midday: string
  // The service account's email once a key is saved; the key never comes back.
  service_account_email: string | null
}

export interface CalendarSyncTestResult {
  ok: boolean
  error: string | null
  calendar: string | null
}

/** Plain words for what Google said when we tried the caller's own calendar. */
const GOOGLE_ERRORS: Record<string, string> = {
  no_key: 'Upload the service account key first.',
  unauthorized_client:
    "Google hasn't allowed this service account to act for your users yet. In the Admin console, add its client ID under Domain-wide delegation with the calendar.events scope. It can take a few minutes to apply.",
  invalid_grant: "Google doesn't recognise your email on this Workspace. Use a Workspace account to test.",
  invalid_key: "The saved key can't be used. Upload a fresh JSON key.",
  calendar_403: 'Google refused access to your calendar. Check that Calendar is turned on for your account.',
  calendar_404: "Google couldn't find your calendar.",
  google_unreachable: "Couldn't reach Google from the server. Try again in a minute.",
}

export function calendarTestMessage(result: CalendarSyncTestResult): string {
  if (result.ok) return `Connected. Events will appear on calendars like ${result.calendar}.`
  return GOOGLE_ERRORS[result.error ?? ''] ?? `Google refused the request (${result.error}).`
}

const DEFAULTS: CalendarSyncSettings = {
  enabled: false,
  decline_meetings: true,
  decline_message: "I'm out of office and will reply when I'm back.",
  midday: '13:00',
  service_account_email: null,
}

export function useCalendarSync() {
  const settings = ref<CalendarSyncSettings>({ ...DEFAULTS })
  const saving = ref(false)
  const error = ref('')

  async function load(): Promise<void> {
    error.value = ''
    try {
      settings.value = (await api.get<CalendarSyncSettings>('/v1/leave/calendar-sync')).data
    } catch (err) {
      error.value = extractApiError(err, "Couldn't load the calendar settings.")
    }
  }

  /** Save; ``key`` is the downloaded JSON's text, or null to keep the saved one. */
  async function save(key: string | null): Promise<boolean> {
    saving.value = true
    error.value = ''
    try {
      const body = { ...settings.value, service_account_key: key }
      settings.value = (await api.put<CalendarSyncSettings>('/v1/leave/calendar-sync', body)).data
      return true
    } catch (err) {
      error.value = extractApiError(err, "Couldn't save the calendar settings.")
      return false
    } finally {
      saving.value = false
    }
  }

  async function test(): Promise<CalendarSyncTestResult | string> {
    try {
      return (await api.post<CalendarSyncTestResult>('/v1/leave/calendar-sync/test')).data
    } catch (err) {
      return extractApiError(err, "Couldn't reach Google.")
    }
  }

  return { settings, saving, error, load, save, test }
}
