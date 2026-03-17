<template>
  <div>
    <div class="text-center mb-8">
      <div class="text-h5 font-weight-bold mb-1">Connections</div>
      <div class="text-body-2 text-medium-emphasis">
        Connect your tools and configure AI agents. Everything is optional — set up later if you prefer.
      </div>
    </div>

    <!-- ─── SOURCE CODE ─────────────────────────────────────────── -->
    <div class="section-header mb-3">
      <v-icon icon="mdi-source-branch" size="18" color="primary" />
      <span class="text-body-2 font-weight-medium">Source Code</span>
    </div>
    <div class="text-caption text-medium-emphasis mb-4">
      FlowDev agents need access to your code to write PRDs, triage features, link bugs,
      and generate status updates. Point to a local path for fastest access, or connect
      a Git provider for PR tracking.
    </div>

    <!-- Local Source Code Path -->
    <v-card class="pa-5 integration-card mb-4" color="surface">
      <div class="d-flex align-center ga-3 mb-1">
        <v-avatar size="36" color="surface-variant" rounded="lg">
          <v-icon icon="mdi-folder-code" size="22" />
        </v-avatar>
        <div>
          <div class="text-body-2 font-weight-medium">Local Source Code</div>
          <div class="text-caption text-medium-emphasis">
            Direct filesystem access — fastest for agents using Claude Code or local LLMs
          </div>
        </div>
      </div>

      <div class="mt-4">
        <v-btn-toggle
          v-model="setupStore.state.sourceCode.type"
          mandatory
          density="compact"
          color="primary"
          variant="outlined"
          class="mb-3"
        >
          <v-btn value="single-repo" size="small" prepend-icon="mdi-source-repository">
            Single Repo
          </v-btn>
          <v-btn value="workspace" size="small" prepend-icon="mdi-folder-multiple-outline">
            Workspace
          </v-btn>
        </v-btn-toggle>

        <v-text-field
          v-model="setupStore.state.sourceCode.localPath"
          :label="setupStore.state.sourceCode.type === 'workspace'
            ? 'Workspace root (contains multiple repos)'
            : 'Repository path'"
          :placeholder="setupStore.state.sourceCode.type === 'workspace'
            ? '/home/user/projects'
            : '/home/user/projects/my-app'"
          density="compact"
          variant="outlined"
          :hint="setupStore.state.sourceCode.type === 'workspace'
            ? 'FlowDev will scan all repos under this directory'
            : 'Absolute path to the git repository root'"
          persistent-hint
        >
          <template #prepend-inner>
            <v-icon
              icon="mdi-folder-outline"
              class="cursor-pointer"
              @click="directoryPicker?.open()"
            />
          </template>
          <template #append-inner>
            <v-btn
              variant="text"
              density="compact"
              size="small"
              color="primary"
              class="text-none"
              @click="directoryPicker?.open()"
            >
              Browse
            </v-btn>
          </template>
        </v-text-field>

        <DirectoryPicker
          ref="directoryPicker"
          :initial-path="setupStore.state.sourceCode.localPath"
          @select="(path: string) => setupStore.state.sourceCode.localPath = path"
        />
      </div>
    </v-card>

    <!-- Git Providers -->
    <div class="text-caption text-medium-emphasis mb-3">
      Optionally connect a Git provider for remote PR tracking, status updates, and issue sync.
    </div>

    <v-row class="mb-2">
      <!-- GitHub -->
      <v-col cols="12" sm="6">
        <v-card
          class="pa-5 integration-card"
          :class="{ 'integration-card--active': setupStore.state.integrations.github.enabled }"
          color="surface"
        >
          <div class="d-flex align-center justify-space-between mb-1">
            <div class="d-flex align-center ga-3">
              <v-avatar size="36" color="surface-variant" rounded="lg">
                <v-icon icon="mdi-github" size="22" />
              </v-avatar>
              <div>
                <div class="text-body-2 font-weight-medium">GitHub</div>
                <div class="text-caption text-medium-emphasis">PR tracking &amp; issue sync</div>
              </div>
            </div>
            <v-switch
              v-model="setupStore.state.integrations.github.enabled"
              hide-details
              density="compact"
              color="primary"
            />
          </div>

          <v-expand-transition>
            <div v-if="setupStore.state.integrations.github.enabled" class="mt-4">
              <v-text-field
                v-model="setupStore.state.integrations.github.pat"
                label="Personal Access Token"
                placeholder="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                prepend-inner-icon="mdi-key-outline"
                type="password"
                density="compact"
                variant="outlined"
                class="mb-2"
                :rules="[rules.required]"
              />

              <v-expansion-panels variant="accordion" class="mb-3 helper-panel">
                <v-expansion-panel>
                  <v-expansion-panel-title class="text-caption">
                    <v-icon icon="mdi-help-circle-outline" size="16" class="mr-2" />
                    How to create a Personal Access Token
                  </v-expansion-panel-title>
                  <v-expansion-panel-text>
                    <ol class="text-caption text-medium-emphasis helper-steps">
                      <li>Go to <strong>GitHub &rarr; Settings &rarr; Developer settings &rarr;
                        Personal access tokens &rarr; Fine-grained tokens</strong></li>
                      <li>Click <strong>"Generate new token"</strong></li>
                      <li>Name it (e.g. <code>FlowDev</code>) and set an expiration</li>
                      <li>Under <strong>Repository access</strong>, select the repos
                        FlowDev should track</li>
                      <li>Under <strong>Permissions</strong>, grant:
                        <ul>
                          <li>Pull requests: <strong>Read &amp; Write</strong></li>
                          <li>Issues: <strong>Read &amp; Write</strong></li>
                          <li>Contents: <strong>Read</strong></li>
                        </ul>
                      </li>
                      <li>Click <strong>"Generate token"</strong> and copy it</li>
                    </ol>
                    <v-alert type="info" variant="tonal" density="compact" class="mt-2">
                      We recommend <strong>fine-grained tokens</strong> scoped to
                      specific repos for better security.
                    </v-alert>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>
            </div>
          </v-expand-transition>
        </v-card>
      </v-col>

      <!-- Coming Soon: Bitbucket + GitLab -->
      <v-col cols="12" sm="6">
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

    <!-- ─── MESSAGING ───────────────────────────────────────────── -->
    <div class="section-header mb-3 mt-8">
      <v-icon icon="mdi-message-text-outline" size="18" color="primary" />
      <span class="text-body-2 font-weight-medium">Messaging</span>
    </div>
    <div class="text-caption text-medium-emphasis mb-4">
      FlowDev listens for feature requests, sends standup summaries, and lets you trigger agents
      directly from your team's chat.
    </div>

    <v-row class="mb-2">
      <!-- Slack -->
      <v-col cols="12" sm="6">
        <v-card
          class="pa-5 integration-card"
          :class="{ 'integration-card--active': setupStore.state.integrations.slack.enabled }"
          color="surface"
        >
          <div class="d-flex align-center justify-space-between mb-1">
            <div class="d-flex align-center ga-3">
              <v-avatar size="36" color="surface-variant" rounded="lg">
                <v-icon icon="mdi-slack" size="22" />
              </v-avatar>
              <div>
                <div class="text-body-2 font-weight-medium">Slack</div>
                <div class="text-caption text-medium-emphasis">Feature intake &amp; agent triggers</div>
              </div>
            </div>
            <v-switch
              v-model="setupStore.state.integrations.slack.enabled"
              hide-details
              density="compact"
              color="primary"
            />
          </div>

          <v-expand-transition>
            <div v-if="setupStore.state.integrations.slack.enabled" class="mt-4">
              <v-text-field
                v-model="setupStore.state.integrations.slack.botToken"
                label="Bot Token"
                placeholder="xoxb-..."
                prepend-inner-icon="mdi-key-outline"
                density="compact"
                variant="outlined"
                class="mb-2"
                :rules="[rules.required]"
              />
              <v-text-field
                v-model="setupStore.state.integrations.slack.signingSecret"
                label="Signing Secret"
                placeholder="Enter signing secret"
                prepend-inner-icon="mdi-shield-key-outline"
                type="password"
                density="compact"
                variant="outlined"
                class="mb-2"
                :rules="[rules.required]"
              />

              <v-expansion-panels variant="accordion" class="helper-panel">
                <v-expansion-panel>
                  <v-expansion-panel-title class="text-caption">
                    <v-icon icon="mdi-help-circle-outline" size="16" class="mr-2" />
                    How to get your Slack credentials
                  </v-expansion-panel-title>
                  <v-expansion-panel-text>
                    <ol class="text-caption text-medium-emphasis helper-steps">
                      <li>
                        Go to
                        <strong>
                          <a href="https://api.slack.com/apps" target="_blank" rel="noopener">api.slack.com/apps</a>
                        </strong>
                        and click <strong>"Create New App"</strong>
                      </li>
                      <li>Choose <strong>"From scratch"</strong>, name it (e.g. <code>FlowDev</code>), and select your workspace</li>
                      <li>Under <strong>Basic Information &rarr; App Credentials</strong>, copy the <strong>Signing Secret</strong></li>
                      <li>Go to <strong>OAuth &amp; Permissions</strong> and add these <strong>Bot Token Scopes</strong>:
                        <ul>
                          <li><code>chat:write</code>, <code>channels:read</code>, <code>channels:history</code></li>
                          <li><code>users:read</code>, <code>commands</code></li>
                        </ul>
                      </li>
                      <li>Click <strong>"Install to Workspace"</strong> and authorize</li>
                      <li>Copy the <strong>Bot User OAuth Token</strong> (starts with <code>xoxb-</code>)</li>
                    </ol>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>
            </div>
          </v-expand-transition>
        </v-card>
      </v-col>

      <!-- Telegram -->
      <v-col cols="12" sm="6">
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

    <!-- ─── AI CONFIGURATION ────────────────────────────────────── -->
    <div class="section-header mb-3 mt-8">
      <v-icon icon="mdi-robot-outline" size="18" color="primary" />
      <span class="text-body-2 font-weight-medium">AI Configuration</span>
    </div>
    <div class="text-caption text-medium-emphasis mb-4">
      FlowDev's 11 agents each use an LLM to do their work. Pick a preset to configure all agents at once.
      You can customize individual agents later in the admin panel.
    </div>

    <!-- Preset Cards -->
    <v-row class="mb-4">
      <v-col v-for="preset in presets" :key="preset.value" cols="12" sm="6" md="3">
        <v-card
          class="pa-5 text-center cursor-pointer preset-card h-100"
          :class="{ 'preset-card--active': setupStore.state.aiConfig.preset === preset.value }"
          color="surface"
          @click="setupStore.state.aiConfig.preset = preset.value"
        >
          <v-icon
            :icon="preset.icon"
            size="36"
            :color="setupStore.state.aiConfig.preset === preset.value ? 'primary' : 'grey'"
            class="mb-3"
          />
          <div class="text-body-1 font-weight-medium mb-1">{{ preset.title }}</div>
          <div class="text-caption text-medium-emphasis mb-3">{{ preset.description }}</div>
          <v-chip
            v-if="preset.recommended"
            size="x-small"
            color="primary"
            variant="tonal"
          >
            Recommended
          </v-chip>
        </v-card>
      </v-col>
    </v-row>

    <!-- Claude Code Connection (shown for presets that use Claude Code) -->
    <v-expand-transition>
      <v-card
        v-if="needsClaudeCode"
        class="pa-6 card-border-dark mb-4"
        color="surface"
      >
        <div class="d-flex align-center ga-3 mb-1">
          <v-avatar size="36" color="surface-variant" rounded="lg">
            <v-icon icon="mdi-console" size="22" />
          </v-avatar>
          <div class="flex-grow-1">
            <div class="text-body-1 font-weight-medium">Claude Code</div>
            <div class="text-caption text-medium-emphasis">
              Required for codebase-aware agents. Must be installed on this machine.
            </div>
          </div>
          <v-chip
            v-if="claudeStatus === 'passed'"
            color="success"
            variant="flat"
            size="small"
            prepend-icon="mdi-check-circle-outline"
          >
            Connected
          </v-chip>
          <v-chip
            v-else-if="claudeStatus === 'failed'"
            color="error"
            variant="flat"
            size="small"
            prepend-icon="mdi-alert-circle-outline"
          >
            Not Available
          </v-chip>
        </div>

        <div class="mt-4">
          <div class="d-flex align-center ga-3">
            <v-btn
              color="primary"
              variant="tonal"
              prepend-icon="mdi-connection"
              :loading="claudeStatus === 'checking'"
              @click="checkClaudeCode"
            >
              {{ claudeStatus === 'idle' ? 'Test Connection' : 'Retest' }}
            </v-btn>
          </div>

          <v-expand-transition>
            <div v-if="claudeStatus === 'failed'" class="mt-3">
              <v-alert type="warning" variant="tonal" density="compact">
                <div class="text-body-2 mb-2">{{ claudeError }}</div>
                <div class="text-caption">
                  Install Claude Code:
                  <code>curl -fsSL https://claude.ai/install.sh | bash</code>
                </div>
              </v-alert>
            </div>
          </v-expand-transition>

          <v-expand-transition>
            <div v-if="claudeStatus === 'passed' && claudeVersion" class="mt-3">
              <div class="text-caption text-medium-emphasis">
                <v-icon icon="mdi-information-outline" size="14" class="mr-1" />
                Version: {{ claudeVersion }}
              </div>
            </div>
          </v-expand-transition>
        </div>
      </v-card>
    </v-expand-transition>

    <!-- Preset Config Fields -->
    <v-card class="pa-6 card-border-dark" color="surface">
      <div class="text-body-1 font-weight-medium mb-1">{{ activePresetTitle }} Settings</div>
      <div class="text-caption text-medium-emphasis mb-4">{{ activePresetHint }}</div>

      <!-- Local preset: Ollama URL + model -->
      <template v-if="setupStore.state.aiConfig.preset === 'local'">
        <v-text-field
          v-model="setupStore.state.aiConfig.ollamaUrl"
          label="Ollama URL"
          placeholder="http://localhost:11434"
          prepend-inner-icon="mdi-server-outline"
          density="compact"
          variant="outlined"
          class="mb-3"
        />
        <v-text-field
          v-model="setupStore.state.aiConfig.ollamaModel"
          label="Model"
          placeholder="llama3:8b"
          prepend-inner-icon="mdi-cube-outline"
          density="compact"
          variant="outlined"
        />
      </template>

      <!-- Cloud preset: Provider + API key + model -->
      <template v-if="setupStore.state.aiConfig.preset === 'cloud'">
        <v-select
          v-model="setupStore.state.aiConfig.cloudProvider"
          :items="cloudProviders"
          label="Provider"
          prepend-inner-icon="mdi-cloud-outline"
          density="compact"
          variant="outlined"
          class="mb-3"
        />
        <v-text-field
          v-model="setupStore.state.aiConfig.cloudApiKey"
          label="API Key"
          :placeholder="setupStore.state.aiConfig.cloudProvider === 'anthropic' ? 'sk-ant-...' : 'sk-...'"
          prepend-inner-icon="mdi-key-outline"
          type="password"
          density="compact"
          variant="outlined"
          class="mb-3"
          :rules="[rules.required]"
        />
        <v-text-field
          v-model="setupStore.state.aiConfig.cloudModel"
          label="Model"
          :placeholder="setupStore.state.aiConfig.cloudProvider === 'anthropic' ? 'claude-sonnet-4-5-20250514' : 'gpt-4o'"
          prepend-inner-icon="mdi-cube-outline"
          density="compact"
          variant="outlined"
        />
      </template>

      <!-- Hybrid preset: Cloud API key -->
      <template v-if="setupStore.state.aiConfig.preset === 'hybrid'">
        <v-alert type="info" variant="tonal" density="compact" class="mb-4">
          Codebase agents (Triage, PRD, Learning, Skill, Tech Plan, Test Plan) use Claude Code.
          Other agents (Status, Standup, Bug Linker, Reassignment, Design) use the Cloud API.
        </v-alert>
        <v-select
          v-model="setupStore.state.aiConfig.cloudProvider"
          :items="cloudProviders"
          label="Cloud Provider"
          prepend-inner-icon="mdi-cloud-outline"
          density="compact"
          variant="outlined"
          class="mb-3"
        />
        <v-text-field
          v-model="setupStore.state.aiConfig.cloudApiKey"
          label="Cloud API Key"
          :placeholder="setupStore.state.aiConfig.cloudProvider === 'anthropic' ? 'sk-ant-...' : 'sk-...'"
          prepend-inner-icon="mdi-key-outline"
          type="password"
          density="compact"
          variant="outlined"
          class="mb-3"
          :rules="[rules.required]"
        />
        <v-text-field
          v-model="setupStore.state.aiConfig.cloudModel"
          label="Cloud Model"
          :placeholder="setupStore.state.aiConfig.cloudProvider === 'anthropic' ? 'claude-sonnet-4-5-20250514' : 'gpt-4o'"
          prepend-inner-icon="mdi-cube-outline"
          density="compact"
          variant="outlined"
        />
      </template>

      <!-- Claude + Ollama preset: Ollama URL + model -->
      <template v-if="setupStore.state.aiConfig.preset === 'claude-ollama'">
        <v-alert type="info" variant="tonal" density="compact" class="mb-4">
          Codebase agents (Triage, PRD, Learning, Skill, Tech Plan, Test Plan) use Claude Code.
          Other agents (Status, Standup, Bug Linker, Reassignment, Design) use Ollama.
        </v-alert>
        <v-text-field
          v-model="setupStore.state.aiConfig.ollamaUrl"
          label="Ollama URL"
          placeholder="http://localhost:11434"
          prepend-inner-icon="mdi-server-outline"
          density="compact"
          variant="outlined"
          class="mb-3"
        />
        <v-text-field
          v-model="setupStore.state.aiConfig.ollamaModel"
          label="Ollama Model"
          placeholder="llama3:8b"
          prepend-inner-icon="mdi-cube-outline"
          density="compact"
          variant="outlined"
        />
      </template>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useSetupStore } from '@/stores/setup'
import type { AIPreset } from '@/types/setup'
import api from '@/services/api'
import DirectoryPicker from '@/components/setup/DirectoryPicker.vue'

const setupStore = useSetupStore()

const directoryPicker = ref<InstanceType<typeof DirectoryPicker> | null>(null)

const rules = {
  required: (v: string) => !!v?.trim() || 'This field is required',
}

// ── Claude Code connection state ─────────────────────────────
const claudeStatus = ref<'idle' | 'checking' | 'passed' | 'failed'>('idle')
const claudeError = ref('')
const claudeVersion = ref('')

const needsClaudeCode = computed(() =>
  setupStore.state.aiConfig.preset === 'hybrid' || setupStore.state.aiConfig.preset === 'claude-ollama'
)

async function checkClaudeCode(): Promise<void> {
  claudeStatus.value = 'checking'
  claudeError.value = ''
  claudeVersion.value = ''

  try {
    const { data } = await api.get('/setup/check-claude', { timeout: 120_000 })
    if (data.cli_available && data.test_passed) {
      claudeStatus.value = 'passed'
      claudeVersion.value = data.output || ''
    } else {
      claudeStatus.value = 'failed'
      claudeError.value = data.error || 'Claude Code CLI is not available or test failed.'
    }
  } catch {
    claudeStatus.value = 'failed'
    claudeError.value = 'Could not reach the server to test Claude Code.'
  }
}

// ── Preset definitions ───────────────────────────────────────
const presets: { value: AIPreset; icon: string; title: string; description: string; recommended?: boolean }[] = [
  {
    value: 'hybrid',
    icon: 'mdi-shuffle-variant',
    title: 'Hybrid',
    description: 'Claude Code for codebase agents, Cloud API for the rest. Best balance of quality and cost.',
    recommended: true,
  },
  {
    value: 'claude-ollama',
    icon: 'mdi-console-network',
    title: 'Claude Code + Ollama',
    description: 'Claude Code for codebase agents, Ollama for the rest. Fully local, no API keys for non-code agents.',
  },
  {
    value: 'cloud',
    icon: 'mdi-cloud-outline',
    title: 'Cloud API',
    description: 'Use Anthropic or OpenAI. Best quality, requires API key.',
  },
  {
    value: 'local',
    icon: 'mdi-server-outline',
    title: 'Local (Ollama)',
    description: 'Run everything on your machine. No API keys needed.',
  },
]

const cloudProviders = [
  { title: 'Anthropic', value: 'anthropic' as const },
  { title: 'OpenAI', value: 'openai' as const },
]

const activePresetTitle = computed(() => {
  const p = presets.find(p => p.value === setupStore.state.aiConfig.preset)
  return p?.title ?? 'AI'
})

const activePresetHint = computed(() => {
  switch (setupStore.state.aiConfig.preset) {
    case 'local': return 'All 11 agents will use Ollama running on your machine.'
    case 'cloud': return 'All 11 agents will use the selected cloud provider.'
    case 'hybrid': return 'Codebase agents use Claude Code; other agents use the Cloud API.'
    case 'claude-ollama': return 'Codebase agents use Claude Code; other agents use Ollama locally.'
    default: return ''
  }
})
</script>

<style scoped>
/* Section headers */
.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

/* Integration cards */
.integration-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  transition: border-color 0.2s ease;
}

.integration-card--active {
  border-color: rgba(var(--v-theme-primary), 0.4);
}

/* Preset cards */
.preset-card {
  border: 1px solid rgba(255, 255, 255, 0.08);
  transition: border-color 0.2s ease, background-color 0.2s ease;
}

.preset-card--active {
  border-color: rgb(var(--v-theme-primary)) !important;
  background: rgba(var(--v-theme-primary), 0.04) !important;
}

/* Coming soon cards */
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

/* Helper panels */
.helper-panel :deep(.v-expansion-panel) {
  background: transparent;
}

.helper-panel :deep(.v-expansion-panel-title) {
  min-height: 36px;
  padding: 6px 12px;
}

.helper-steps {
  padding-left: 18px;
  line-height: 1.8;
}

.helper-steps code {
  background: rgba(255, 255, 255, 0.08);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 0.85em;
}

.helper-steps ul {
  padding-left: 16px;
  list-style-type: disc;
}

.helper-steps a {
  color: rgb(var(--v-theme-primary));
}
</style>
