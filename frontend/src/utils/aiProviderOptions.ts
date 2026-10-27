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
 * Pure rules for the AI provider settings: which auth modes to offer in
 * this deployment, which one to recommend, how to describe each, and
 * whether the form can be saved. Capabilities come from the backend.
 */
import { providerIcon, providerTitle, type AuthModeSpec, type ProviderCaps } from '@/constants/aiProviders'

export interface ChoiceTile {
  value: string
  title: string
  icon: string
  description: string
  badge?: string
}

const MODE_ICONS: Record<string, string> = {
  host: 'mdi-laptop',
  api_key: 'mdi-key-variant',
  subscription: 'mdi-account-key-outline',
}

export function providerTiles(providers: ProviderCaps[]): ChoiceTile[] {
  return providers.map(p => ({
    value: p.provider,
    title: providerTitle(p.provider),
    icon: providerIcon(p.provider),
    // Not every provider is a CLI: one that talks HTTP has no binary to name.
    description: p.cli ? `Runs through the ${p.cli} CLI.` : 'Runs against a server on your own machine. No CLI needed.',
  }))
}

export function modeDescription(mode: AuthModeSpec, caps: ProviderCaps): string {
  if (!mode.requires_secret) {
    // "No secret" means two things: a CLI provider inherits the host login,
    // while an HTTP provider simply sends no credential.
    return caps.cli === null
      ? 'Sends no credential, for a server that does not need one.'
      : 'Uses the login already on the host. Nothing is stored in the database.'
  }
  if (mode.value === 'subscription') {
    return 'Paste an OAuth token from `claude setup-token`. Uses your Claude plan and is stored encrypted.'
  }
  return `Paste a ${mode.label}. Stored encrypted and used for every agent run.`
}

/**
 * Full Docker cannot reach a host login, so the host mode is hidden there
 * for providers that have a host login to inherit (the CLI ones). For an
 * HTTP provider "host" means "no credential", which works in a container.
 */
export function visibleModes(caps: ProviderCaps, deploymentMode: string): AuthModeSpec[] {
  return caps.auth_modes.filter(m => !(deploymentMode === 'docker' && m.value === 'host' && caps.cli !== null))
}

export function recommendedMode(caps: ProviderCaps, deploymentMode: string): string {
  if (deploymentMode === 'docker' && caps.cli !== null) {
    return caps.auth_modes.find(m => m.requires_secret)?.value ?? caps.auth_modes[0]?.value ?? 'api_key'
  }
  return caps.auth_modes.find(m => m.value === 'host')?.value ?? caps.auth_modes[0]?.value ?? 'host'
}

export function authTiles(caps: ProviderCaps | undefined, deploymentMode: string): ChoiceTile[] {
  if (!caps) return []
  const recommended = recommendedMode(caps, deploymentMode)
  return visibleModes(caps, deploymentMode).map(m => ({
    value: m.value,
    title: m.label,
    icon: MODE_ICONS[m.value] ?? 'mdi-key',
    description: modeDescription(m, caps),
    badge: m.value === recommended ? 'Recommended' : undefined,
  }))
}

export function credentialPlaceholder(provider: string, authMode: string): string {
  if (provider === 'copilot') return 'ghp_…'
  if (provider === 'codex') return 'sk-…'
  return authMode === 'subscription' ? 'sk-ant-oat…' : 'sk-ant-…'
}

/**
 * A stored credential only counts while the provider is unchanged: a
 * saved Anthropic key cannot stand in for a GitHub or OpenAI token.
 */
export function canSaveProvider(opts: {
  requiresSecret: boolean
  hasStored: boolean
  providerChanged: boolean
  typed: string
}): boolean {
  if (!opts.requiresSecret) return true
  return (opts.hasStored && !opts.providerChanged) || opts.typed.trim().length > 0
}

/** One line for the Integrations card: "Agents run through Claude, using the host login." */
export function providerSummary(caps: ProviderCaps | undefined, mode: AuthModeSpec | undefined): string {
  if (!caps) return 'Choose which agent runs codebase-aware work and how it signs in.'
  let how = ''
  if (mode?.requires_secret) how = `, using a stored ${mode.label}`
  else if (mode) how = caps.cli === null ? ', with no credential' : ', using the host login'
  return `Agents run through ${providerTitle(caps.provider)}${how}.`
}
