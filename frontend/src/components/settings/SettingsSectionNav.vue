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

<!-- The settings pages the reader can open, grouped, beside the
     Integrations page. Phones reach the same pages from the menu. -->
<template>
  <nav aria-label="Settings sections" class="settings-nav">
    <div v-for="group in groups" :key="group.label" class="settings-nav__group">
      <p class="settings-nav__label">{{ group.label }}</p>
      <router-link
        v-for="item in group.items"
        :key="item.to"
        :to="item.to"
        class="settings-nav__link"
        :class="{ 'settings-nav__link--on': item.to === route.path }"
        :aria-current="item.to === route.path ? 'page' : undefined"
      >
        {{ item.title }}
      </router-link>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { usePermissions } from '@/composables/usePermissions'
import { settingsSections } from '@/utils/settingsSections'

const route = useRoute()
const p = usePermissions()

const groups = computed(() =>
  settingsSections({
    connections: p.canViewConnections.value,
    code: p.canViewCodeSettings.value,
    designSystems: p.canViewDesignSystems.value,
    agentPrompts: p.canViewAgentPrompts.value,
    qa: p.canViewQAAutomation.value,
    presence: p.canViewPresenceSettings.value,
    jira: p.canViewJiraImport.value,
    quiz: p.canManageQuiz.value,
    leave: p.canConfigureLeave.value,
    employees: p.canManageEmployees.value,
    celebrations: p.canManageCelebrations.value,
    members: p.canManageMembers.value,
    engineering: p.canAccessEngineering.value,
  }),
)
</script>

<style scoped>
.settings-nav {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.settings-nav__group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.settings-nav__label {
  margin: 0 10px 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: var(--tracking-label);
  text-transform: uppercase;
  color: rgb(var(--v-theme-on-surface-variant));
}
.settings-nav__link {
  display: flex;
  align-items: center;
  height: 32px;
  padding: 0 10px;
  border-radius: 7px;
  font-size: 14px;
  text-decoration: none;
  color: rgb(var(--v-theme-ink-2));
}
.settings-nav__link:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.settings-nav__link:focus-visible {
  outline: 2px solid var(--color-focus);
  outline-offset: 1px;
}
.settings-nav__link--on {
  font-weight: 500;
  color: var(--color-accent-text);
  background: var(--color-accent-soft);
}
</style>
