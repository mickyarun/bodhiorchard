<template>
  <div class="settings-page">
    <!-- Fixed header -->
    <div class="settings-header pa-6 pb-4">
      <div class="d-flex align-center justify-space-between">
        <div>
          <div class="text-h5 font-weight-bold">Settings</div>
          <div class="text-body-2 text-medium-emphasis">
            Manage connections, integrations, and AI configuration
          </div>
        </div>
        <v-btn
          color="primary"
          prepend-icon="mdi-content-save-outline"
          :loading="settingsStore.saving"
          @click="save"
        >
          Save Changes
        </v-btn>
      </div>

      <!-- Alerts in header area -->
      <v-alert v-if="settingsStore.error" type="error" variant="tonal" class="mt-4" closable>
        {{ settingsStore.error }}
      </v-alert>
      <v-alert
        v-if="settingsStore.saveSuccess"
        type="success"
        variant="tonal"
        class="mt-4"
        closable
        @click:close="settingsStore.saveSuccess = false"
      >
        Settings saved successfully.
      </v-alert>
    </div>

    <!-- Scrollable content -->
    <div class="settings-content px-6 pb-6">
      <!-- Loading -->
      <div v-if="settingsStore.loading" class="d-flex justify-center py-12">
        <v-progress-circular indeterminate color="primary" />
      </div>

      <template v-if="!settingsStore.loading">
      <!-- ─── REPOSITORIES ───────────────────────────────────── -->
      <div class="section-header mb-3">
        <v-icon icon="mdi-source-repository-multiple" size="18" color="primary" />
        <span class="text-body-2 font-weight-medium">Repositories</span>
      </div>

      <SettingsRepositories />

      <!-- ─── MCP INTEGRATION ─────────────────────────────────── -->
      <div class="section-header mb-3">
        <v-icon icon="mdi-api" size="18" color="primary" />
        <span class="text-body-2 font-weight-medium">MCP Integration</span>
      </div>

      <v-card class="pa-5 settings-card mb-6" color="surface">
        <div class="d-flex align-center ga-3 mb-4">
          <v-avatar size="36" color="surface-variant" rounded="lg">
            <v-icon icon="mdi-connection" size="22" />
          </v-avatar>
          <div>
            <div class="text-body-2 font-weight-medium">Claude Code MCP</div>
            <div class="text-caption text-medium-emphasis">
              Connect Claude Code to Bodhigrove for BUDs, knowledge, and team context
            </div>
          </div>
        </div>

        <!-- Token status -->
        <div class="d-flex align-center ga-3 mb-4">
          <v-chip
            :color="mcpTokenSet ? 'success' : 'warning'"
            variant="tonal"
            size="small"
            :prepend-icon="mcpTokenSet ? 'mdi-check-circle-outline' : 'mdi-alert-circle-outline'"
          >
            {{ mcpTokenSet ? 'Token configured' : 'No token set' }}
          </v-chip>
          <v-btn
            variant="tonal"
            density="compact"
            size="small"
            color="primary"
            class="text-none"
            :loading="regeneratingToken"
            @click="regenerateMcpToken"
          >
            {{ mcpTokenSet ? 'Regenerate Token' : 'Generate Token' }}
          </v-btn>
        </div>

        <!-- Token display (one-time) -->
        <v-expand-transition>
          <v-alert
            v-if="newMcpToken"
            type="info"
            variant="tonal"
            density="compact"
            class="mb-4"
          >
            <div class="text-body-2 font-weight-medium mb-1">
              Your MCP token (copy now — it won't be shown again):
            </div>
            <div class="d-flex align-center ga-2">
              <code class="flex-grow-1 pa-2" style="background: rgba(0,0,0,0.2); border-radius: 4px; word-break: break-all;">
                {{ newMcpToken }}
              </code>
              <v-btn
                icon="mdi-content-copy"
                variant="text"
                size="small"
                @click="copyToken"
              />
            </div>
          </v-alert>
        </v-expand-transition>

        <!-- Setup instructions -->
        <div class="text-body-2 font-weight-medium mb-2">Setup</div>
        <div class="text-caption text-medium-emphasis mb-3">
          MCP is auto-configured in your repos during scanning (<code>.mcp.json</code>).
          To activate, set your token as a persistent environment variable:
        </div>
        <div class="config-snippet pa-3 rounded mb-3" style="background: rgba(0,0,0,0.3); position: relative;">
          <v-btn
            icon="mdi-content-copy"
            variant="text"
            size="x-small"
            style="position: absolute; top: 4px; right: 4px;"
            @click="copyConfig"
          />
          <pre class="text-caption" style="white-space: pre-wrap; margin: 0;">{{ envVarSnippet }}</pre>
        </div>

        <v-expansion-panels variant="accordion" class="mb-2">
          <v-expansion-panel>
            <v-expansion-panel-title class="text-caption py-1">
              <v-icon icon="mdi-apple" size="14" class="mr-1" /> macOS
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <pre class="text-caption" style="white-space: pre-wrap; margin: 0;">{{ macInstructions }}</pre>
            </v-expansion-panel-text>
          </v-expansion-panel>
          <v-expansion-panel>
            <v-expansion-panel-title class="text-caption py-1">
              <v-icon icon="mdi-linux" size="14" class="mr-1" /> Linux (Ubuntu)
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <pre class="text-caption" style="white-space: pre-wrap; margin: 0;">{{ linuxInstructions }}</pre>
            </v-expansion-panel-text>
          </v-expansion-panel>
          <v-expansion-panel>
            <v-expansion-panel-title class="text-caption py-1">
              <v-icon icon="mdi-microsoft-windows" size="14" class="mr-1" /> Windows
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <pre class="text-caption" style="white-space: pre-wrap; margin: 0;">{{ windowsInstructions }}</pre>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>

        <div class="text-caption text-medium-emphasis">
          After adding, restart your terminal and Claude Code for the change to take effect.
        </div>
      </v-card>

      <!-- ─── GIT PROVIDERS ────────────────────────────────────── -->
      <div class="section-header mb-3">
        <v-icon icon="mdi-git" size="18" color="primary" />
        <span class="text-body-2 font-weight-medium">Git Providers</span>
      </div>

      <v-row class="mb-6">
        <!-- GitHub App -->
        <v-col cols="12" md="6">
          <v-card
            class="pa-5 settings-card"
            :class="{ 'settings-card--active': settingsStore.connections.github.enabled }"
            color="surface"
          >
            <div class="d-flex align-center justify-space-between mb-3">
              <div class="d-flex align-center ga-3">
                <v-avatar size="36" color="surface-variant" rounded="lg">
                  <v-icon icon="mdi-github" size="22" />
                </v-avatar>
                <div>
                  <div class="text-body-2 font-weight-medium">GitHub App</div>
                  <div class="text-caption text-medium-emphasis">PR tracking, code review &amp; webhooks</div>
                </div>
              </div>
              <v-chip
                :color="settingsStore.connections.github.enabled ? 'success' : 'grey'"
                size="x-small"
                variant="tonal"
              >
                {{ settingsStore.connections.github.enabled ? 'Connected' : 'Not set up' }}
              </v-chip>
            </div>

            <v-text-field
              v-model.number="githubAppId"
              label="App ID"
              placeholder="123456"
              prepend-inner-icon="mdi-identifier"
              density="compact"
              variant="outlined"
              class="mb-3"
              type="number"
            />

            <v-textarea
              v-model="githubPrivateKey"
              label="Private Key (.pem)"
              placeholder="-----BEGIN RSA PRIVATE KEY-----&#10;...&#10;-----END RSA PRIVATE KEY-----"
              prepend-inner-icon="mdi-key-outline"
              density="compact"
              variant="outlined"
              rows="3"
              class="mb-3"
              :hint="settingsStore.connections.github.hasPrivateKey ? 'Key saved. Leave empty to keep existing.' : 'Paste the .pem file contents'"
              persistent-hint
            />

            <v-text-field
              v-model="githubWebhookSecret"
              label="Webhook Secret"
              placeholder="Set during GitHub App creation"
              prepend-inner-icon="mdi-shield-key-outline"
              density="compact"
              variant="outlined"
              class="mb-3"
              type="password"
            />

            <v-chip
              v-if="settingsStore.connections.github.installationId"
              size="x-small"
              variant="tonal"
              color="success"
              prepend-icon="mdi-check-circle-outline"
              class="mb-3"
            >
              Installation #{{ settingsStore.connections.github.installationId }} (auto-detected)
            </v-chip>

            <div class="text-caption text-medium-emphasis setup-steps">
              <v-icon icon="mdi-help-circle-outline" size="14" class="mr-1" />
              <strong>How to set up:</strong>
              <ol class="pl-4 mt-1 mb-0" style="line-height: 1.8;">
                <li>Go to your GitHub <strong>org settings</strong> &rarr; Developer settings &rarr; GitHub Apps &rarr;
                  <a href="https://github.com/settings/apps/new" target="_blank" rel="noopener" class="text-primary">New GitHub App</a>
                </li>
                <li>Set <strong>Webhook URL</strong> to <code>{{ backendUrl }}/api/v1/webhooks/github</code></li>
                <li>Set <strong>Webhook Secret</strong> &mdash; generate one with <code>openssl rand -hex 32</code> and paste it in both GitHub and here</li>
                <li>Under <strong>Repository permissions</strong>: set <em>Pull requests</em> to <strong>Read &amp; Write</strong>, <em>Contents</em> to <strong>Read</strong>, <em>Issues</em> to <strong>Read</strong> (enables PR comment webhooks)</li>
                <li>Under <strong>Subscribe to events</strong>: check <em>Pull request</em>, <em>Pull request review</em>, and <em>Pull request review comment</em></li>
                <li>Click <strong>Create GitHub App</strong> &mdash; copy the <strong>App ID</strong> shown at the top and paste it above</li>
                <li>On the app page, scroll to <strong>Private keys</strong> &rarr; Generate a private key &mdash; paste the downloaded <code>.pem</code> contents above</li>
                <li>Go to <strong>Install App</strong> (left sidebar) &rarr; install on your org and grant access to your repos</li>
              </ol>
            </div>
          </v-card>
        </v-col>

        <!-- Coming Soon -->
        <v-col cols="12" md="6">
          <div class="d-flex flex-column ga-3 h-100">
            <v-card class="pa-4 coming-soon-card flex-grow-1" color="surface" variant="outlined">
              <div class="d-flex align-center ga-3">
                <v-avatar size="36" rounded="lg" class="coming-soon-avatar">
                  <v-icon icon="mdi-bitbucket" size="20" />
                </v-avatar>
                <div class="flex-grow-1">
                  <div class="text-body-2 font-weight-medium">Bitbucket</div>
                  <div class="text-caption text-medium-emphasis">Cloud &amp; Server PR tracking</div>
                </div>
                <v-chip size="x-small" variant="tonal" color="grey">Soon</v-chip>
              </div>
            </v-card>
            <v-card class="pa-4 coming-soon-card flex-grow-1" color="surface" variant="outlined">
              <div class="d-flex align-center ga-3">
                <v-avatar size="36" rounded="lg" class="coming-soon-avatar">
                  <v-icon icon="mdi-gitlab" size="20" />
                </v-avatar>
                <div class="flex-grow-1">
                  <div class="text-body-2 font-weight-medium">GitLab</div>
                  <div class="text-caption text-medium-emphasis">SaaS &amp; self-managed MR tracking</div>
                </div>
                <v-chip size="x-small" variant="tonal" color="grey">Soon</v-chip>
              </div>
            </v-card>
          </div>
        </v-col>
      </v-row>

      <!-- ─── MESSAGING ──────────────────────────────────────── -->
      <div class="section-header mb-3">
        <v-icon icon="mdi-message-text-outline" size="18" color="primary" />
        <span class="text-body-2 font-weight-medium">Messaging</span>
      </div>

      <v-row class="mb-6">
        <!-- Slack -->
        <v-col cols="12" md="6">
          <SettingsSlack />
        </v-col>

        <!-- Telegram coming soon -->
        <v-col cols="12" md="6">
          <v-card class="pa-4 coming-soon-card h-100 d-flex align-center" color="surface" variant="outlined">
            <div class="d-flex align-center ga-3 w-100">
              <v-avatar size="36" rounded="lg" class="coming-soon-avatar">
                <v-icon icon="mdi-send" size="20" />
              </v-avatar>
              <div class="flex-grow-1">
                <div class="text-body-2 font-weight-medium">Telegram</div>
                <div class="text-caption text-medium-emphasis">Notifications &amp; workflow triggers</div>
              </div>
              <v-chip size="x-small" variant="tonal" color="grey">Soon</v-chip>
            </div>
          </v-card>
        </v-col>
      </v-row>

      <!-- ─── AI CONFIGURATION ───────────────────────────────── -->
      <div class="section-header mb-3">
        <v-icon icon="mdi-robot-outline" size="18" color="primary" />
        <span class="text-body-2 font-weight-medium">AI Configuration</span>
      </div>

      <SettingsAiConfig />

      <!-- Bottom save button -->
      <div class="d-flex justify-end">
        <v-btn
          color="primary"
          prepend-icon="mdi-content-save-outline"
          :loading="settingsStore.saving"
          @click="save"
        >
          Save Changes
        </v-btn>
      </div>
    </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import api from '@/services/api'
import SettingsRepositories from './SettingsRepositories.vue'
import SettingsSlack from './SettingsSlack.vue'
import SettingsAiConfig from './SettingsAiConfig.vue'

const settingsStore = useSettingsStore()

// ─── GitHub App state ───────────────────────────
const githubAppId = ref<number | null>(settingsStore.connections.github.appId)
const githubPrivateKey = ref('')
const githubWebhookSecret = ref('')
const backendUrl = window.location.origin

// MCP token state
const mcpTokenSet = ref(false)
const newMcpToken = ref('')
const regeneratingToken = ref(false)

const envVarSnippet = computed(() => {
  const token = newMcpToken.value || '<your-bodhigrove-token>'
  return `export BODHIGROVE_MCP_TOKEN="${token}"`
})

const macInstructions = computed(() => {
  const token = newMcpToken.value || '<your-bodhigrove-token>'
  return `# Add to ~/.zshrc (default shell on macOS)
echo 'export BODHIGROVE_MCP_TOKEN="${token}"' >> ~/.zshrc
source ~/.zshrc`
})

const linuxInstructions = computed(() => {
  const token = newMcpToken.value || '<your-bodhigrove-token>'
  return `# Add to ~/.bashrc (or ~/.zshrc if using zsh)
echo 'export BODHIGROVE_MCP_TOKEN="${token}"' >> ~/.bashrc
source ~/.bashrc`
})

const windowsInstructions = computed(() => {
  const token = newMcpToken.value || '<your-bodhigrove-token>'
  return `# PowerShell — set permanently for current user
[Environment]::SetEnvironmentVariable("BODHIGROVE_MCP_TOKEN", "${token}", "User")

# Or via CMD
setx BODHIGROVE_MCP_TOKEN "${token}"`
})

onMounted(async () => {
  await settingsStore.fetchConnections()
  checkMcpTokenStatus()
})

async function save(): Promise<void> {
  // Inject GitHub App credentials into the payload before saving
  if (githubAppId.value) {
    (settingsStore.connections.github as Record<string, unknown>).appId = githubAppId.value
  }
  if (githubPrivateKey.value) {
    (settingsStore.connections.github as Record<string, unknown>).privateKey = githubPrivateKey.value
  }
  if (githubWebhookSecret.value) {
    (settingsStore.connections.github as Record<string, unknown>).webhookSecret = githubWebhookSecret.value
  }
  await settingsStore.saveConnections()
  // Clear sensitive fields after save
  githubPrivateKey.value = ''
  githubWebhookSecret.value = ''
  // Sync appId from response
  githubAppId.value = settingsStore.connections.github.appId
}

async function checkMcpTokenStatus(): Promise<void> {
  try {
    const { data } = await api.get('/v1/settings/mcp-token/status')
    mcpTokenSet.value = data.has_token
  } catch {
    // Token status check is non-critical
  }
}

async function regenerateMcpToken(): Promise<void> {
  regeneratingToken.value = true
  try {
    const { data } = await api.post('/v1/settings/mcp-token')
    newMcpToken.value = data.mcp_token
    mcpTokenSet.value = true
  } catch {
    settingsStore.error = 'Failed to generate MCP token.'
  } finally {
    regeneratingToken.value = false
  }
}

function copyToken(): void {
  navigator.clipboard.writeText(newMcpToken.value)
}

function copyConfig(): void {
  navigator.clipboard.writeText(envVarSnippet.value)
}
</script>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.settings-header {
  flex-shrink: 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  background: rgb(var(--v-theme-background));
  z-index: 1;
}

.settings-content {
  flex: 1;
  overflow-y: auto;
  padding-top: 24px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.coming-soon-card {
  opacity: 0.45;
  border-style: dashed !important;
  border-color: rgba(255, 255, 255, 0.12) !important;
  transition: opacity 0.2s ease;
}

.coming-soon-card:hover {
  opacity: 0.6;
}

.coming-soon-avatar {
  background: rgba(255, 255, 255, 0.04);
}
</style>

<style>
/* Global (not scoped) — used by child components and Vuetify portals */
.settings-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  transition: border-color 0.2s ease;
}

.settings-card--active {
  border-color: rgba(var(--v-theme-primary), 0.4);
}

.scan-tooltip {
  color: #fff !important;
  background: #1e1e2e !important;
  font-size: 13px !important;
  line-height: 1.5 !important;
  padding: 10px 14px !important;
}

.preset-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  transition: border-color 0.2s ease, background-color 0.2s ease;
}

.preset-card--active {
  border-color: rgb(var(--v-theme-primary)) !important;
  background: rgba(var(--v-theme-primary), 0.04) !important;
}

.index-stat {
  min-width: 64px;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  text-align: center;
}
</style>
