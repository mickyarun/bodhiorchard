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
 * Shared org member directory ({ id, name, email }).
 *
 * The `/v1/members/directory` endpoint is a light, permission-free roster
 * of every org member — unlike the live OrgRoom presence (connected
 * members only) or the full `/v1/members` admin list. Race surfaces need
 * it to resolve names for invitees who aren't currently online:
 *   - RaceSetupDialog / RaceInviteMoreDialog — populate the member picker.
 *   - RaceLobbyPanel — label pending-invitee slots with a name instead of
 *     a truncated user id.
 *
 * The fetch is cached at module scope so the three consumers share a
 * single round-trip and a single reactive list; `ensureLoaded()` is
 * idempotent and dedupes concurrent callers onto one in-flight promise.
 */
import { ref } from 'vue'
import api from '@/services/api'

export interface DirectoryEntry {
  id: string
  name: string
  email: string
}

// Module-scoped so every component instance reads the same roster and a
// second mount never re-fetches.
const entries = ref<DirectoryEntry[]>([])
const loading = ref(false)
let inflight: Promise<void> | null = null
const byId = new Map<string, DirectoryEntry>()

function reindex(): void {
  byId.clear()
  for (const e of entries.value) byId.set(e.id, e)
}

async function ensureLoaded(force = false): Promise<void> {
  if (!force && (entries.value.length > 0 || inflight)) {
    await inflight
    return
  }
  inflight = (async () => {
    loading.value = true
    try {
      const { data } = await api.get<DirectoryEntry[]>('/v1/members/directory')
      entries.value = data
      reindex()
    } catch (err) {
      console.error('[useMemberDirectory] directory fetch failed:', err)
    } finally {
      loading.value = false
      inflight = null
    }
  })()
  await inflight
}

/**
 * Display name for a user id. Falls back to a shortened id when the
 * directory hasn't loaded yet or the id isn't an org member (e.g. a
 * stale invite) — never returns the raw 36-char UUID.
 */
function nameFor(userId: string): string {
  // Touch the reactive list so a caller inside a computed/render re-runs
  // once the directory finishes loading (the `byId` Map alone isn't a
  // reactive dependency).
  void entries.value.length
  const hit = byId.get(userId)
  if (hit?.name) return hit.name
  return userId.length > 12 ? `${userId.slice(0, 8)}…` : userId
}

export function useMemberDirectory() {
  return { entries, loading, ensureLoaded, nameFor }
}
