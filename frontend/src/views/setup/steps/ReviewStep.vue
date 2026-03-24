<template>
  <div>
    <div class="text-center mb-6">
      <v-icon icon="mdi-rocket-launch-outline" size="48" color="primary" class="mb-3" />
      <div class="text-h5 font-weight-bold mb-1">Review & Launch</div>
      <div class="text-body-2 text-medium-emphasis">
        Confirm your configuration and launch Bodhigrove
      </div>
    </div>

    <!-- Organization -->
    <v-card class="pa-5 card-border-dark mb-4" color="surface">
      <div class="d-flex align-center ga-3 mb-3">
        <v-icon icon="mdi-domain" color="primary" size="20" />
        <div class="text-body-1 font-weight-medium">Organization</div>
      </div>
      <v-table density="compact" class="bg-transparent">
        <tbody>
          <tr>
            <td class="text-medium-emphasis" style="width: 140px;">Name</td>
            <td>{{ setupStore.state.organization.name }}</td>
          </tr>
          <tr>
            <td class="text-medium-emphasis">Slug</td>
            <td>
              <code class="text-primary">{{ setupStore.state.organization.slug }}</code>
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

    <!-- Admin -->
    <v-card class="pa-5 card-border-dark mb-4" color="surface">
      <div class="d-flex align-center ga-3 mb-3">
        <v-icon icon="mdi-account-key-outline" color="primary" size="20" />
        <div class="text-body-1 font-weight-medium">Admin Account</div>
      </div>
      <v-table density="compact" class="bg-transparent">
        <tbody>
          <tr>
            <td class="text-medium-emphasis" style="width: 140px;">Name</td>
            <td>{{ setupStore.state.admin.name }}</td>
          </tr>
          <tr>
            <td class="text-medium-emphasis">Email</td>
            <td>{{ setupStore.state.admin.email }}</td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

    <!-- Source Code & Integrations -->
    <v-card class="pa-5 card-border-dark mb-4" color="surface">
      <div class="d-flex align-center ga-3 mb-3">
        <v-icon icon="mdi-connection" color="primary" size="20" />
        <div class="text-body-1 font-weight-medium">Connections</div>
      </div>
      <v-table density="compact" class="bg-transparent mb-3">
        <tbody>
          <tr v-if="setupStore.state.sourceCode.localPath">
            <td class="text-medium-emphasis" style="width: 140px;">Source Code</td>
            <td>
              <code class="text-primary">{{ setupStore.state.sourceCode.localPath }}</code>
              <v-chip size="x-small" variant="tonal" class="ml-2">
                {{ setupStore.state.sourceCode.type === 'workspace' ? 'Workspace' : 'Single Repo' }}
              </v-chip>
            </td>
          </tr>
        </tbody>
      </v-table>
      <div class="d-flex ga-4 flex-wrap">
        <v-chip
          :color="setupStore.state.integrations.github.enabled ? 'success' : 'default'"
          :variant="setupStore.state.integrations.github.enabled ? 'flat' : 'tonal'"
          prepend-icon="mdi-github"
        >
          GitHub: {{ setupStore.state.integrations.github.enabled ? 'Connected' : 'Skipped' }}
        </v-chip>
        <v-chip
          :color="setupStore.state.integrations.slack.enabled ? 'success' : 'default'"
          :variant="setupStore.state.integrations.slack.enabled ? 'flat' : 'tonal'"
          prepend-icon="mdi-slack"
        >
          Slack: {{ setupStore.state.integrations.slack.enabled ? 'Connected' : 'Skipped' }}
        </v-chip>
      </div>
    </v-card>

    <!-- AI Configuration -->
    <v-card class="pa-5 card-border-dark mb-4" color="surface">
      <div class="d-flex align-center ga-3 mb-3">
        <v-icon icon="mdi-robot-outline" color="primary" size="20" />
        <div class="text-body-1 font-weight-medium">AI Configuration</div>
      </div>
      <v-table density="compact" class="bg-transparent">
        <tbody>
          <tr>
            <td class="text-medium-emphasis" style="width: 140px;">Preset</td>
            <td class="text-capitalize">{{ presetLabel }}</td>
          </tr>
          <tr v-if="setupStore.state.aiConfig.preset === 'hybrid' || setupStore.state.aiConfig.preset === 'claude-ollama'">
            <td class="text-medium-emphasis">Claude Code</td>
            <td>Codebase agents</td>
          </tr>
          <tr v-if="setupStore.state.aiConfig.preset === 'cloud' || setupStore.state.aiConfig.preset === 'hybrid'">
            <td class="text-medium-emphasis">Cloud Provider</td>
            <td class="text-capitalize">{{ setupStore.state.aiConfig.cloudProvider }}</td>
          </tr>
          <tr v-if="setupStore.state.aiConfig.preset === 'cloud' || setupStore.state.aiConfig.preset === 'hybrid'">
            <td class="text-medium-emphasis">Cloud Model</td>
            <td>
              <code class="text-primary">{{ setupStore.state.aiConfig.cloudModel }}</code>
            </td>
          </tr>
          <tr v-if="setupStore.state.aiConfig.preset === 'local' || setupStore.state.aiConfig.preset === 'claude-ollama'">
            <td class="text-medium-emphasis">Ollama URL</td>
            <td>
              <code class="text-primary">{{ setupStore.state.aiConfig.ollamaUrl }}</code>
            </td>
          </tr>
          <tr v-if="setupStore.state.aiConfig.preset === 'local' || setupStore.state.aiConfig.preset === 'claude-ollama'">
            <td class="text-medium-emphasis">Ollama Model</td>
            <td>
              <code class="text-primary">{{ setupStore.state.aiConfig.ollamaModel }}</code>
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

    <v-alert
      type="info"
      variant="tonal"
      density="compact"
      icon="mdi-cog-outline"
      class="mb-6"
    >
      You can change all settings later in the admin panel.
    </v-alert>

    <div class="d-flex justify-center">
      <v-btn
        color="primary"
        size="large"
        prepend-icon="mdi-rocket-launch-outline"
        :loading="setupStore.isSubmitting"
        @click="emit('launch')"
      >
        Launch Bodhigrove
      </v-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSetupStore } from '@/stores/setup'
import type { AIPreset } from '@/types/setup'

const setupStore = useSetupStore()

const emit = defineEmits<{
  launch: []
}>()

const presetLabels: Record<AIPreset, string> = {
  hybrid: 'Hybrid (Recommended)',
  'claude-ollama': 'Claude Code + Ollama',
  cloud: 'Cloud API',
  local: 'Local (Ollama)',
}

const presetLabel = computed(() => presetLabels[setupStore.state.aiConfig.preset])
</script>
