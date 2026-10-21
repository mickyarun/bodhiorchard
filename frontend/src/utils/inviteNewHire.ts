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

/** Helpers for HR inviting a new hire: which roles to offer, and a temporary password. */
import type { RoleOption } from '@/stores/members'

/**
 * The roles the inviter may hand out, in list order. The server decides
 * (``GET /roles/assignable``, the same grant ceiling the invite enforces),
 * so the picker never offers a role that would only end in an error.
 */
export function offeredRoles(roles: readonly RoleOption[], assignable: readonly string[]): RoleOption[] {
  const allowed = new Set(assignable)
  return roles.filter(role => allowed.has(role.id))
}

/** "sales" → "Sales", "tech_lead" → "Tech lead", "hr" → "HR". */
export function roleLabel(name: string): string {
  if (name.length <= 2) return name.toUpperCase()
  const words = name.replace(/_/g, ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

const ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'

/** A temporary password the new hire replaces at first sign-in (no look-alike characters). */
export function temporaryPassword(length = 12): string {
  const bytes = new Uint8Array(length)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, b => ALPHABET[b % ALPHABET.length]).join('')
}
