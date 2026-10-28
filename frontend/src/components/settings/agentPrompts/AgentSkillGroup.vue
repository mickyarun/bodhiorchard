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

<!-- One agent type's section: its header, the skill rows (slot) and the
     inline button that adds a custom skill for that agent. -->
<template>
  <section class="agent-group">
    <!-- Section header -->
    <div class="group-header">
      <div class="group-icon-wrap">
        <v-icon :icon="agentIcon(agentType)" size="20" />
      </div>
      <div class="group-meta">
        <div class="group-title">{{ agentTypeLabel(agentType) }}</div>
        <div class="group-sub">{{ agentBlurb(agentType) }}</div>
      </div>
      <v-chip variant="tonal" size="x-small" label class="group-count">
        {{ count }}
        skill{{ count === 1 ? '' : 's' }}
      </v-chip>
    </div>

    <!-- Skill rows -->
    <div class="skill-list">
      <slot />

      <!-- Inline add-button per group -->
      <button
        type="button"
        class="skill-add"
        @click="emit('add')"
      >
        <v-icon icon="mdi-plus" size="16" />
        Add a custom skill for {{ agentTypeLabel(agentType) }}
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { AgentType } from '@/stores/agentSkills'
import { agentBlurb, agentIcon, agentTypeLabel } from './agentPrompts.util'

defineProps<{
  agentType: AgentType
  count: number
}>()
const emit = defineEmits<{ add: [] }>()
</script>

<style scoped>
.agent-group {
  display: flex;
  flex-direction: column;
}

.group-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 4px 12px;
}

.group-icon-wrap {
  width: 32px;
  height: 32px;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgb(var(--v-theme-surface-variant));
  color: rgb(var(--v-theme-ink-2));
}

.group-meta { flex: 1; min-width: 0; }
.group-title {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0;
  color: rgb(var(--v-theme-on-surface));
}
.group-sub {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.55);
}

.group-count {
  font-variant-numeric: tabular-nums;
  text-transform: none;
  letter-spacing: 0;
  font-weight: 500;
}

/* ── Skill list ──────────────────────────────────────────────── */

.skill-list {
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgba(var(--v-theme-surface), 0.6);
  overflow: hidden;
}

/* ── Add-skill button (per group) ────────────────────────────── */

.skill-add {
  all: unset;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 12px 16px;
  font-size: 13px;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.55);
  border-top: 1px dashed rgba(var(--v-theme-on-surface), 0.1);
  transition: background 120ms ease, color 120ms ease;
}
.skill-add:hover {
  background: rgba(var(--v-theme-primary), 0.06);
  color: rgb(var(--v-theme-primary));
}
</style>
