// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
