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

<!-- The GitHub App setup in its own card, for places without the
     Integrations page around it (the repository onboarding tab). -->
<template>
  <section class="gh-card" aria-labelledby="gh-card-title">
    <header class="gh-card__head">
      <span class="gh-card__icon" aria-hidden="true"><v-icon icon="mdi-github" size="22" /></span>
      <span class="gh-card__who">
        <span id="gh-card-title" class="gh-card__title">GitHub App</span>
        <span class="gh-card__sub">Pull request tracking, code review and webhooks</span>
      </span>
      <GitHubAppStatusBadge :status="settingsStore.connections.github.status" />
    </header>
    <GitHubAppPanel
      ref="panelRef"
      :standalone="standalone"
      @status-change="s => emit('status-change', s)"
      @ready="emit('ready')"
    />
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import GitHubAppPanel from './GitHubAppPanel.vue'
import GitHubAppStatusBadge from './GitHubAppStatusBadge.vue'
import { useSettingsStore } from '@/stores/settings'
import type { GitHubAppStatus } from '@/types/connections'

withDefaults(defineProps<{ standalone?: boolean }>(), { standalone: false })
const emit = defineEmits<{ 'status-change': [GitHubAppStatus]; ready: [] }>()

const settingsStore = useSettingsStore()
const panelRef = ref<InstanceType<typeof GitHubAppPanel> | null>(null)

defineExpose({
  flushCredentials: () => panelRef.value?.flushCredentials(),
  clearSensitiveFields: () => panelRef.value?.clearSensitiveFields(),
})
</script>

<style scoped>
.gh-card {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px 20px;
  border-radius: 12px;
  border: 1px solid rgb(var(--v-theme-rule));
  background: rgb(var(--v-theme-surface));
}
.gh-card__head {
  display: flex;
  align-items: center;
  gap: 12px;
}
.gh-card__icon {
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  color: rgb(var(--v-theme-ink-2));
  background: rgb(var(--v-theme-surface-variant));
}
.gh-card__who {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-width: 0;
}
.gh-card__title {
  font-size: 15px;
  font-weight: 600;
}
.gh-card__sub {
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
