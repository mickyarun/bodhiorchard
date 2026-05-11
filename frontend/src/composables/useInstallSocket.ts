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
 * Per-org GitHub App install event channel.
 *
 * Subscribes to ``org:{orgId}:install`` so the setup wizard / Settings
 * card flips AWAITING_INSTALL → READY the moment the install webhook
 * lands, instead of waiting up to 4 s for the next poll tick.
 *
 * One-shot signal — there is no progressive state, just "webhook
 * arrived, refetch connections". The caller wires the refetch in the
 * ``onEvent`` callback.
 */
import { onUnmounted } from 'vue'
import { subscribe, unsubscribe } from '@/services/socket'
import type { GitHubAppStatus } from '@/types/connections'

/**
 * Field names match the snake_case wire format used by other event_bus
 * publishers (xp, scan, notifications). Do NOT alias to camelCase here —
 * keeping the wire shape verbatim makes the contract obvious when
 * grepping across backend publish sites and frontend consumers.
 */
export interface InstallEvent {
  event_type: 'install_set'
  status: GitHubAppStatus
  installation_id: number | null
}

export function useInstallSocket(onEvent: (event: InstallEvent) => void) {
  const handler = onEvent as (data: unknown) => void
  let activeTopic: string | null = null

  function start(orgId: string): void {
    stop()
    activeTopic = `org:${orgId}:install`
    subscribe(activeTopic, handler)
  }

  function stop(): void {
    if (activeTopic) {
      unsubscribe(activeTopic, handler)
      activeTopic = null
    }
  }

  onUnmounted(stop)

  return { start, stop }
}
