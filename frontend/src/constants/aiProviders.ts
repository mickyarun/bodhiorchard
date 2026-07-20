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
 * Presentation for the AI providers, shared by Settings and the setup wizard.
 *
 * Both screens render the same provider tiles, so this lives in one place —
 * the two copies it replaces had already drifted apart.
 *
 * Everything behavioural (which models, which auth modes, what a provider can
 * do) comes from the backend capability table via the capabilities endpoint.
 * Only names and icons belong here.
 */

export interface ProviderMeta {
  title: string
  icon: string
}

export const PROVIDER_META: Record<string, ProviderMeta> = {
  claude: { title: 'Claude', icon: 'mdi-robot-happy-outline' },
  copilot: { title: 'GitHub Copilot', icon: 'mdi-github' },
  codex: { title: 'OpenAI Codex', icon: 'mdi-alpha-c-box-outline' },
  ollama: { title: 'Ollama (local)', icon: 'mdi-server-network-outline' },
}

/** An auth mode as the capabilities endpoint describes it. */
export interface AuthModeSpec {
  value: string
  label: string
  requires_secret: boolean
}

/** One provider's capabilities, as served by the backend. */
export interface ProviderCaps {
  provider: string
  cli: string | null
  models: { id: string; label: string }[]
  default_model: string
  supports_effort: boolean
  effort_values: string[]
  supports_iteration_model: boolean
  auth_modes: AuthModeSpec[]
  install_hint: string
  docs_url: string
  supports_thinking: boolean
  supports_mcp: boolean
  supports_files: boolean
  dynamic_models: boolean
  requires_base_url: boolean
  default_base_url: string | null
  // Features this provider can't run, phrased for the user and supplied by the
  // backend that decides them. Optional so an older payload renders no list
  // rather than a stale one.
  limitations?: string[]
}

export function providerTitle(provider: string): string {
  return PROVIDER_META[provider]?.title ?? provider
}

export function providerIcon(provider: string): string {
  return PROVIDER_META[provider]?.icon ?? 'mdi-robot'
}

/**
 * What a provider cannot do, in the user's terms.
 *
 * A provider without file access silently produces confident answers about
 * files it never read, so the UI has to say so up front rather than let it be
 * discovered when a scan quietly returns nothing.
 *
 * The list is served by the capabilities endpoint, not written here. This file
 * used to keep its own copy, and it went stale the moment a feature was
 * reworked to run off the prompt payload instead of the filesystem — it went on
 * naming scanning, synthesis and design-system extraction as unavailable long
 * after all three worked. The backend owns which phases truly need files, so it
 * owns the sentence about them too.
 */
export function providerLimitations(caps: ProviderCaps | undefined): string[] {
  if (!caps || caps.supports_files) return []
  return caps.limitations ?? []
}
