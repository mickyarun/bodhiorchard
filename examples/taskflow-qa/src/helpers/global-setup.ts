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
 * Playwright global setup — runs once before any test worker starts.
 *
 * Seeds the fixture users (TEST_USER, ADMIN_USER) into the taskflow-api
 * database so login flows work against a fresh DB. Tolerates "user already
 * exists" errors (400/409) because the server persists users across runs —
 * the second run will find them and keep going.
 *
 * Without this, every test that calls `loginPage.login(...)` with the
 * fixture credentials hits a 401 and the test suite wedges on the login
 * step. See the TaskFlow API /auth/register route for the expected shape.
 */
import { TEST_USER, ADMIN_USER } from './test-data'

const API_URL = process.env.API_URL || 'http://localhost:9001'

async function ensureUser(email: string, password: string, fullName: string): Promise<void> {
  // Probe first: if login succeeds, the user already exists with the right
  // password — nothing to do. This avoids the register-duplicate problem
  // because taskflow-api's register_user has no uniqueness check and throws
  // an unhandled IntegrityError (500) on email collision.
  const loginProbe = await fetch(`${API_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (loginProbe.ok) {
    console.log(`[global-setup] ${email} already exists and can log in`)
    return
  }

  // Not 401 means something else is wrong (server down, malformed request).
  if (loginProbe.status !== 401) {
    const body = await loginProbe.text()
    throw new Error(
      `[global-setup] unexpected ${loginProbe.status} probing login for ${email}: ${body}`,
    )
  }

  // Login failed with 401 — either the user doesn't exist, or they exist
  // with a different password. Try to register; if that succeeds, great.
  // If it fails with 500 (likely IntegrityError from an existing user with
  // a different password), fail loud so the developer fixes the DB state.
  const registerResp = await fetch(`${API_URL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, full_name: fullName }),
  })
  if (registerResp.ok) {
    console.log(`[global-setup] registered ${email}`)
    return
  }

  const body = await registerResp.text()
  throw new Error(
    `[global-setup] login failed with 401 AND register failed with ${registerResp.status} for ${email}: ${body}. ` +
      `If this user exists with a different password, delete the row from taskflow.db or change TEST_USER credentials.`,
  )
}

export default async function globalSetup(): Promise<void> {
  await ensureUser(TEST_USER.email, TEST_USER.password, TEST_USER.name)
  await ensureUser(ADMIN_USER.email, ADMIN_USER.password, ADMIN_USER.name)
}
