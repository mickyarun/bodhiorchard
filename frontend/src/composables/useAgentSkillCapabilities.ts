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
 * The active provider's model/effort capabilities for the agent skill
 * editor, loaded from GET /v1/settings/ai/capabilities. Effort is hidden
 * entirely when the provider doesn't support it (e.g. a provider with no
 * reasoning levels).
 */
import { ref } from 'vue'
import {
  defaultSkillCaps,
  skillCapsFromPayload,
  type CapabilitiesPayload,
  type SkillCaps,
} from '@/components/settings/agentPrompts/skillCapabilities.util'
import api from '@/services/api'

export function useAgentSkillCapabilities() {
  const caps = ref<SkillCaps>(defaultSkillCaps())

  async function load(): Promise<void> {
    try {
      const { data } = await api.get<CapabilitiesPayload>('/v1/settings/ai/capabilities')
      const next = skillCapsFromPayload(data)
      if (next) caps.value = next
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number } }
      if (axiosErr?.response?.status !== 401) {
        console.warn('[SettingsAgentPrompts] failed to load provider capabilities', err)
      }
    }
  }

  return { caps, load }
}
