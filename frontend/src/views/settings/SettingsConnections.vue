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

<!-- Settings → Integrations: the AI provider, GitHub, Slack and the MCP
     token for Claude Code. Each card opens its own settings and saves on
     its own; one card is open at a time. -->
<template>
  <AppPage title="Settings" subtitle="Workspace settings and connections">
    <div class="settings-layout">
      <SettingsSectionNav class="settings-layout__nav" />

      <div class="settings-layout__main">
        <header>
          <h2 class="settings-title">Integrations</h2>
          <p class="settings-sub">Connect the tools your team already uses. Each one saves on its own.</p>
        </header>

        <AppCallout v-if="settingsStore.error" variant="error">{{ settingsStore.error }}</AppCallout>
        <AppCallout v-if="settingsStore.saveSuccess" variant="success">
          Settings saved.
          <template #actions>
            <v-btn icon="mdi-close" variant="text" size="small" aria-label="Dismiss" @click="settingsStore.saveSuccess = false" />
          </template>
        </AppCallout>

        <div v-if="settingsStore.loading && !settingsStore.connectionsLoaded" class="d-flex justify-center py-12">
          <v-progress-circular indeterminate color="primary" aria-label="Loading settings" />
        </div>
        <template v-else>
          <IntegrationCard
            :open="openId === 'ai'"
            @update:open="v => setOpen('ai', v)"
            name="AI provider"
            icon="mdi-console"
            :description="aiSummary"
            :status="statuses.ai"
            connect-label="Set up"
            :primary="primary === 'ai'"
          >
            <SettingsClaudeCode @test="t => (aiTest = t)" @summary="s => (aiSummary = s)" />
          </IntegrationCard>
          <IntegrationCard
            :open="openId === 'github'"
            @update:open="v => setOpen('github', v)"
            name="GitHub"
            icon="mdi-github"
            description="Track pull requests, run agent code reviews and link merges to BUDs."
            :status="statuses.github"
            connect-label="Connect GitHub"
            :primary="primary === 'github'"
          >
            <GitHubAppPanel standalone />
          </IntegrationCard>
          <IntegrationCard
            :open="openId === 'slack'"
            @update:open="v => setOpen('slack', v)"
            name="Slack"
            icon="mdi-slack"
            description="Turn messages into BUDs, send leave approvals and post celebrations."
            :status="statuses.slack"
            connect-label="Connect Slack"
            :primary="primary === 'slack'"
          >
            <SettingsSlack />
          </IntegrationCard>
          <IntegrationCard
            :open="openId === 'mcp'"
            @update:open="v => setOpen('mcp', v)"
            name="MCP for Claude Code"
            icon="mdi-connection"
            description="Let Claude Code on your laptop read BUDs, knowledge and team context, and update tasks."
            :status="statuses.mcp"
            connect-label="Set up"
            :primary="primary === 'mcp'"
          >
            <McpTokenPanel v-model:has-token="mcpTokenSet" />
          </IntegrationCard>
          <p class="settings-sub">Bitbucket, GitLab and Telegram are coming later.</p>
        </template>
      </div>
    </div>
  </AppPage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPage from '@/components/common/AppPage.vue'
import GitHubAppPanel from '@/components/settings/connections/GitHubAppPanel.vue'
import IntegrationCard from '@/components/settings/connections/IntegrationCard.vue'
import McpTokenPanel from '@/components/settings/connections/McpTokenPanel.vue'
import SettingsSectionNav from '@/components/settings/SettingsSectionNav.vue'
import { useSettingsStore } from '@/stores/settings'
import { providerSummary } from '@/utils/aiProviderOptions'
import {
  aiStatus,
  githubStatus,
  mcpStatus,
  primaryIntegration,
  slackStatus,
  type IntegrationId,
  type ProviderTest,
} from '@/utils/integrations'
import SettingsClaudeCode from './SettingsClaudeCode.vue'
import SettingsSlack from './SettingsSlack.vue'

const ORDER: IntegrationId[] = ['ai', 'github', 'slack', 'mcp']

const settingsStore = useSettingsStore()

const aiTest = ref<ProviderTest>('idle')
const aiSummary = ref(providerSummary(undefined, undefined))
const mcpTokenSet = ref(false)

// One card open at a time: opening one closes the rest.
const openId = ref<IntegrationId | null>(null)
function setOpen(id: IntegrationId, open: boolean): void {
  openId.value = open ? id : null
}

const statuses = computed(() => ({
  ai: aiStatus(aiTest.value),
  github: githubStatus(settingsStore.connections.github.status),
  slack: slackStatus(settingsStore.connections.slack.connected),
  mcp: mcpStatus(mcpTokenSet.value),
}))
const primary = computed(() => primaryIntegration(ORDER, statuses.value, openId.value))

onMounted(() => {
  settingsStore.saveSuccess = false
  void settingsStore.fetchConnections()
})
</script>

<style scoped>
.settings-layout {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 28px;
  align-items: start;
}
.settings-layout__main {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
  max-width: 960px;
}
.settings-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}
.settings-sub {
  margin: 4px 0 0;
  font-size: 14px;
  color: rgb(var(--v-theme-on-surface-variant));
}
@media (max-width: 960px) {
  .settings-layout {
    grid-template-columns: minmax(0, 1fr);
  }
  .settings-layout__nav {
    display: none;
  }
}
</style>
