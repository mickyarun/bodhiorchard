<!--
 * Copyright 2025-2026 Arun Rajkumar
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 -->

<template>
  <div class="agent-error-message">
    <div class="agent-error-headline">{{ error.headline }}</div>
    <div class="agent-error-actions">
      <router-link
        v-if="showSettingsLink"
        :to="error.settingsRoute!"
        class="agent-error-link"
      >
        Open Settings → Agent Prompts
      </router-link>
      <span v-if="showSettingsLink && error.suggestContactAdmin" class="agent-error-sep">
        ·
      </span>
      <span v-if="error.suggestContactAdmin" class="agent-error-contact">
        {{ contactCopy }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { friendlyAgentError } from '@/types/agentErrors'
import { usePermissions } from '@/composables/usePermissions'

const props = defineProps<{
  /** Stable error category code from JobStatusRead.errorCode (or null/undefined). */
  code?: string | null
  /** Human-readable backend message; used as fallback when ``code`` is unknown. */
  fallback?: string | null
}>()

const { canViewAgentPrompts } = usePermissions()

const error = computed(() => friendlyAgentError(props.code, props.fallback))

const showSettingsLink = computed(
  () => error.value.suggestSettings
    && !!error.value.settingsRoute
    && canViewAgentPrompts.value,
)

const contactCopy = computed(() =>
  canViewAgentPrompts.value
    ? 'Or contact your admin if this keeps happening.'
    : 'Contact your admin to adjust the agent settings.',
)
</script>

<style scoped>
.agent-error-message {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 12px;
  border-radius: 6px;
  background: rgba(var(--v-theme-error), 0.08);
  border: 1px solid rgba(var(--v-theme-error), 0.18);
  color: rgba(var(--v-theme-on-surface), 0.92);
  font-size: 13px;
  line-height: 1.5;
}

.agent-error-headline {
  font-weight: 600;
}

.agent-error-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), 0.72);
}

.agent-error-link {
  color: rgb(var(--v-theme-primary));
  text-decoration: underline;
}

.agent-error-link:hover {
  text-decoration: none;
}

.agent-error-sep {
  opacity: 0.5;
}
</style>
