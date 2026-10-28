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

<!-- Compact, always-visible summary row of one skill; clicking it opens or
     closes the inline editor. -->
<template>
  <button
    type="button"
    class="skill-summary"
    @click="emit('toggle')"
  >
    <v-icon
      :icon="open ? 'mdi-chevron-down' : 'mdi-chevron-right'"
      size="18"
      class="skill-chevron"
    />
    <div class="skill-headline">
      <div class="skill-name-row">
        <v-icon
          v-if="skill.isDefault"
          icon="mdi-star"
          size="14"
          color="secondary"
          class="mr-1"
        />
        <span class="skill-name">{{ skill.name }}</span>
        <v-chip
          v-if="skill.isDefault"
          color="primary"
          variant="flat"
          size="x-small"
          label
          class="ml-2"
        >
          Default
        </v-chip>
        <v-chip
          v-if="skill.isCustom"
          color="secondary"
          variant="tonal"
          size="x-small"
          label
          class="ml-2"
        >
          Custom
        </v-chip>
        <v-chip
          v-else-if="skill.isCustomized"
          color="warning"
          variant="tonal"
          size="x-small"
          label
          class="ml-2"
        >
          Modified
        </v-chip>
      </div>
      <div v-if="skill.description" class="skill-desc">
        {{ skill.description }}
      </div>
    </div>
    <div class="skill-meta">
      <span class="skill-meta-chip">
        <v-icon icon="mdi-cube-outline" size="12" />
        {{ coerceModel(caps, skill.model) || 'default' }}
      </span>
      <code class="skill-slug">{{ skill.skillSlug }}</code>
    </div>
  </button>
</template>

<script setup lang="ts">
import type { AgentSkill } from '@/stores/agentSkills'
import { coerceModel, type SkillCaps } from './skillCapabilities.util'

defineProps<{
  skill: AgentSkill
  open: boolean
  caps: SkillCaps
}>()
const emit = defineEmits<{ toggle: [] }>()
</script>

<style scoped>
.skill-summary {
  all: unset;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  width: 100%;
  box-sizing: border-box;
  transition: background 120ms ease;
}

.skill-summary:hover { background: rgba(var(--v-theme-on-surface), 0.04); }
.skill-summary:focus-visible {
  outline: 2px solid rgba(var(--v-theme-primary), 0.45);
  outline-offset: -2px;
}

.skill-chevron { color: rgba(var(--v-theme-on-surface), 0.45); flex-shrink: 0; }

.skill-headline { flex: 1; min-width: 0; }

.skill-name-row { display: flex; align-items: center; flex-wrap: wrap; }
.skill-name {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: -0.005em;
  color: rgb(var(--v-theme-on-surface));
}
.skill-desc {
  font-size: 12.5px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  margin-top: 2px;
  line-height: 1.45;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 720px;
}

.skill-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.skill-meta-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.7);
  background: rgba(var(--v-theme-on-surface), 0.06);
  text-transform: lowercase;
}

.skill-slug {
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  font-size: 11px;
  color: rgba(var(--v-theme-on-surface), 0.45);
}
</style>
