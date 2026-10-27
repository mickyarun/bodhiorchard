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
 * Status words and the single primary action for the integration cards
 * on Settings → Integrations.
 */

import { GITHUB_APP_STATUS, type GitHubAppStatus } from '@/types/connections'

export type IntegrationId = 'ai' | 'github' | 'slack' | 'mcp'

export interface IntegrationStatus {
  /** Tag text, or empty for no tag. */
  label: string
  /** Theme colour for the tag; omitted for a neutral tag. */
  color?: string
  connected: boolean
}

export const NOT_CONNECTED: IntegrationStatus = { label: 'Not connected', connected: false }
export const CONNECTED: IntegrationStatus = { label: 'Connected', color: 'success', connected: true }

const INSTALL_PENDING: IntegrationStatus = { label: 'Install pending', color: 'warning', connected: false }

export function githubStatus(status: GitHubAppStatus): IntegrationStatus {
  if (status === GITHUB_APP_STATUS.READY) return CONNECTED
  if (status === GITHUB_APP_STATUS.AWAITING_INSTALL) return INSTALL_PENDING
  return NOT_CONNECTED
}

export function slackStatus(connected: boolean): IntegrationStatus {
  return connected ? CONNECTED : NOT_CONNECTED
}

export function mcpStatus(hasToken: boolean): IntegrationStatus {
  return hasToken ? { label: 'Token set', color: 'success', connected: true } : { label: 'No token', connected: false }
}

/** The AI provider counts as connected once saved; the tag reflects the last test. */
export type ProviderTest = 'idle' | 'checking' | 'passed' | 'failed'

export function aiStatus(test: ProviderTest): IntegrationStatus {
  if (test === 'passed') return CONNECTED
  if (test === 'failed') return { label: 'Not available', color: 'error', connected: true }
  if (test === 'checking') return { label: 'Testing', connected: true }
  return { label: '', connected: true }
}

/**
 * Which card gets the one filled button: none while a card is open (its
 * own save is the primary then), otherwise the first card in page order
 * that is not connected yet.
 */
export function primaryIntegration(
  order: IntegrationId[],
  statuses: Record<IntegrationId, IntegrationStatus>,
  openId: IntegrationId | null,
): IntegrationId | null {
  if (openId) return null
  return order.find(id => !statuses[id].connected) ?? null
}

/** The header button: what to do next, or Hide while the card is open. */
export function integrationActionLabel(isOpen: boolean, connected: boolean, connectLabel: string): string {
  if (isOpen) return 'Hide'
  return connected ? 'Manage' : connectLabel
}
