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

const API_URL = process.env.API_URL || 'http://localhost:9001'

interface ApiOptions {
  method?: string
  body?: Record<string, unknown>
  token?: string
}

export async function apiRequest(path: string, options: ApiOptions = {}): Promise<Response> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (options.token) {
    headers['Authorization'] = `Bearer ${options.token}`
  }

  return fetch(`${API_URL}${path}`, {
    method: options.method || 'GET',
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  })
}

export async function loginViaApi(email: string, password: string): Promise<string> {
  const resp = await apiRequest('/api/v1/auth/login', {
    method: 'POST',
    body: { email, password },
  })
  const data = await resp.json()
  return data.access_token
}

export async function createTestTask(
  token: string,
  title: string,
  description?: string,
): Promise<Record<string, unknown>> {
  const resp = await apiRequest('/api/v1/tasks', {
    method: 'POST',
    body: { title, description: description || 'Test task created by QA automation' },
    token,
  })
  return resp.json()
}

export async function deleteTestTask(token: string, taskId: string): Promise<void> {
  await apiRequest(`/api/v1/tasks/${taskId}`, {
    method: 'DELETE',
    token,
  })
}
