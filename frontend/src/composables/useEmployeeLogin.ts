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

/** HR generating (never set) or resetting (already set) someone's sign-in password. */
import { ref } from 'vue'

import api from '@/services/api'
import { extractApiError } from '@/utils/errors'

export type PasswordAction = 'generate' | 'reset'

export interface EmployeeLogin {
  action: PasswordAction
  email: string
  slack_linked: boolean
}

export interface EmployeePasswordResult {
  action: PasswordAction
  password: string
  login_url: string
  slack_sent: boolean | null
  slack_error: string | null
}

export const ACTION_LABEL: Record<PasswordAction, string> = {
  generate: 'Generate password',
  reset: 'Reset password',
}

export function useEmployeeLogin(userId: () => string) {
  const login = ref<EmployeeLogin | null>(null)
  const result = ref<EmployeePasswordResult | null>(null)
  const busy = ref(false)
  const error = ref('')

  async function load(): Promise<void> {
    try {
      login.value = (await api.get<EmployeeLogin>(`/v1/employees/${userId()}/login`)).data
    } catch {
      login.value = null // Not ours to manage: the button just doesn't show.
    }
  }

  async function issue(sendSlack: boolean): Promise<boolean> {
    busy.value = true
    error.value = ''
    try {
      const body = sendSlack ? { send_via: 'slack' } : {}
      result.value = (
        await api.post<EmployeePasswordResult>(`/v1/employees/${userId()}/login/password`, body)
      ).data
      // Still "generate" until they sign in and choose their own.
      return true
    } catch (err) {
      error.value = extractApiError(err, "Couldn't set a new password. Try again.")
      return false
    } finally {
      busy.value = false
    }
  }

  return { login, result, busy, error, load, issue }
}
