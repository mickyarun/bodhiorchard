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
 * Model/effort options for the agent skill editor. They are provider-aware:
 * built from the AI capabilities endpoint for the org's active provider so
 * the dropdowns never offer a value the backend would reject.
 */

export interface CapModel { id: string; label: string }

export interface SelectOption { title: string; value: string }

/** What the active provider lets a skill choose. */
export interface SkillCaps {
  models: CapModel[]
  defaultModel: string
  effortValues: string[]
  supportsEffort: boolean
  supportsIterationModel: boolean
}

/** One provider's entry in the capabilities response, as far as skills care. */
interface ProviderCapsPayload {
  provider: string
  models?: CapModel[]
  default_model?: string
  supports_effort?: boolean
  effort_values?: string[]
  supports_iteration_model?: boolean
}

export interface CapabilitiesPayload {
  current_provider?: string
  providers?: ProviderCapsPayload[]
}

const DEFAULT_MODELS: CapModel[] = [{ id: '', label: 'Default' }]

/** Before the capabilities load: one "Default" model, effort shown. */
export function defaultSkillCaps(): SkillCaps {
  return {
    models: DEFAULT_MODELS,
    defaultModel: '',
    effortValues: [],
    supportsEffort: true,
    supportsIterationModel: true,
  }
}

/** The active provider's caps, or null when the response doesn't list it. */
export function skillCapsFromPayload(data: CapabilitiesPayload): SkillCaps | null {
  const current = data.current_provider ?? 'claude'
  const caps = (data.providers ?? []).find(p => p.provider === current)
  if (!caps) return null
  return {
    models: caps.models?.length ? caps.models : DEFAULT_MODELS,
    defaultModel: caps.default_model ?? '',
    effortValues: caps.supports_effort ? caps.effort_values ?? [] : [],
    supportsEffort: !!caps.supports_effort,
    supportsIterationModel: !!caps.supports_iteration_model,
  }
}

// Providers that expose a single model (e.g. Copilot, whose only choice is
// "auto — Copilot picks the model") give the user nothing to select, so the
// model dropdowns are shown read-only rather than as a one-item picker.
export function supportsModelChoice(caps: SkillCaps): boolean {
  return caps.models.length > 1
}

// A skill's stored model is tuned for whatever provider it was saved under
// (e.g. a Claude ``sonnet``). When the active provider doesn't list it, the
// backend's ``resolve_model`` falls back to that provider's default at run
// time — so surface the DEFAULT here rather than a stale foreign id, which
// reads as "this skill runs on sonnet" when it doesn't. Returns '' (the
// provider default) for any model/effort the active provider can't honour.
export function coerceModel(caps: SkillCaps, saved: string | null | undefined): string {
  const v = saved ?? ''
  // Coerce to the provider's DEFAULT model (not a bare ''), so a provider
  // whose default isn't the empty-string option — e.g. Copilot's "auto" —
  // preselects a real, listed value instead of showing a blank dropdown.
  if (v && caps.models.some(m => m.id === v)) return v
  return caps.defaultModel
}

export function coerceEffort(caps: SkillCaps, saved: string | null | undefined): string {
  const v = saved ?? ''
  if (!v || !caps.supportsEffort) return ''
  return caps.effortValues.includes(v) ? v : ''
}

function titleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

// Show a saved value the active provider no longer lists as a clearly-labelled
// fallback option, so the select isn't blank and the user understands it.
function withFallback(base: SelectOption[], saved: string | undefined): SelectOption[] {
  if (!saved || base.some(o => o.value === saved)) return base
  return [...base, { title: `${saved} (falls back to default)`, value: saved }]
}

export function modelOptions(caps: SkillCaps, saved: string | undefined): SelectOption[] {
  return withFallback(caps.models.map(m => ({ title: m.label, value: m.id })), saved)
}

export function iterationModelOptions(caps: SkillCaps, saved: string | undefined): SelectOption[] {
  return withFallback(
    caps.models.map(m => ({ title: m.id === '' ? 'Same as model' : m.label, value: m.id })),
    saved,
  )
}

export function effortOptions(caps: SkillCaps): SelectOption[] {
  const base = [{ title: 'Default', value: '' }]
  return base.concat(caps.effortValues.map(v => ({ title: titleCase(v), value: v })))
}
