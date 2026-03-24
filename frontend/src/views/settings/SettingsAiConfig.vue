<template>
  <!-- Preset cards -->
  <div>
    <v-row class="mb-4">
      <v-col v-for="preset in presets" :key="preset.value" cols="12" sm="6" md="3">
        <v-card
          class="pa-5 text-center cursor-pointer preset-card h-100"
          :class="{ 'preset-card--active': settingsStore.connections.aiConfig.preset === preset.value }"
          color="surface"
          @click="settingsStore.connections.aiConfig.preset = preset.value"
        >
          <v-icon
            :icon="preset.icon"
            size="36"
            :color="settingsStore.connections.aiConfig.preset === preset.value ? 'primary' : 'grey'"
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

    <!-- Claude Code connection (for presets that use it) -->
    <v-expand-transition>
      <SettingsClaudeCode v-if="needsClaudeCode" class="mb-4" />
    </v-expand-transition>

    <!-- Preset config fields -->
    <v-card class="pa-6 settings-card mb-6" color="surface">
      <div class="text-body-1 font-weight-medium mb-1">{{ activePresetTitle }} Settings</div>
      <div class="text-caption text-medium-emphasis mb-4">{{ activePresetHint }}</div>

      <!-- Local -->
      <template v-if="settingsStore.connections.aiConfig.preset === 'local'">
        <v-text-field
          v-model="settingsStore.connections.aiConfig.ollamaUrl"
          label="Ollama URL"
          placeholder="http://localhost:11434"
          prepend-inner-icon="mdi-server-outline"
          density="compact" variant="outlined" class="mb-3"
        />
        <v-text-field
          v-model="settingsStore.connections.aiConfig.ollamaModel"
          label="Model"
          placeholder="llama3:8b"
          prepend-inner-icon="mdi-cube-outline"
          density="compact" variant="outlined"
        />
      </template>

      <!-- Cloud -->
      <template v-if="settingsStore.connections.aiConfig.preset === 'cloud'">
        <v-select
          v-model="settingsStore.connections.aiConfig.cloudProvider"
          :items="cloudProviders"
          label="Provider"
          prepend-inner-icon="mdi-cloud-outline"
          density="compact" variant="outlined" class="mb-3"
        />
        <v-text-field
          v-model="settingsStore.connections.aiConfig.cloudApiKey"
          label="API Key"
          :placeholder="settingsStore.connections.aiConfig.cloudProvider === 'anthropic' ? 'sk-ant-...' : 'sk-...'"
          prepend-inner-icon="mdi-key-outline"
          type="password"
          density="compact" variant="outlined" class="mb-3"
          hint="Leave unchanged to keep existing key"
          persistent-hint
        />
        <v-text-field
          v-model="settingsStore.connections.aiConfig.cloudModel"
          label="Model"
          :placeholder="settingsStore.connections.aiConfig.cloudProvider === 'anthropic' ? 'claude-sonnet-4-5-20250514' : 'gpt-4o'"
          prepend-inner-icon="mdi-cube-outline"
          density="compact" variant="outlined"
        />
      </template>

      <!-- Hybrid -->
      <template v-if="settingsStore.connections.aiConfig.preset === 'hybrid'">
        <v-alert type="info" variant="tonal" density="compact" class="mb-4">
          Codebase agents use Claude Code. Other agents use the Cloud API.
        </v-alert>
        <v-select
          v-model="settingsStore.connections.aiConfig.cloudProvider"
          :items="cloudProviders"
          label="Cloud Provider"
          prepend-inner-icon="mdi-cloud-outline"
          density="compact" variant="outlined" class="mb-3"
        />
        <v-text-field
          v-model="settingsStore.connections.aiConfig.cloudApiKey"
          label="Cloud API Key"
          :placeholder="settingsStore.connections.aiConfig.cloudProvider === 'anthropic' ? 'sk-ant-...' : 'sk-...'"
          prepend-inner-icon="mdi-key-outline"
          type="password"
          density="compact" variant="outlined" class="mb-3"
          hint="Leave unchanged to keep existing key"
          persistent-hint
        />
        <v-text-field
          v-model="settingsStore.connections.aiConfig.cloudModel"
          label="Cloud Model"
          :placeholder="settingsStore.connections.aiConfig.cloudProvider === 'anthropic' ? 'claude-sonnet-4-5-20250514' : 'gpt-4o'"
          prepend-inner-icon="mdi-cube-outline"
          density="compact" variant="outlined"
        />
      </template>

      <!-- Claude + Ollama -->
      <template v-if="settingsStore.connections.aiConfig.preset === 'claude-ollama'">
        <v-alert type="info" variant="tonal" density="compact" class="mb-4">
          Codebase agents use Claude Code. Other agents use Ollama locally.
        </v-alert>
        <v-text-field
          v-model="settingsStore.connections.aiConfig.ollamaUrl"
          label="Ollama URL"
          placeholder="http://localhost:11434"
          prepend-inner-icon="mdi-server-outline"
          density="compact" variant="outlined" class="mb-3"
        />
        <v-text-field
          v-model="settingsStore.connections.aiConfig.ollamaModel"
          label="Ollama Model"
          placeholder="llama3:8b"
          prepend-inner-icon="mdi-cube-outline"
          density="compact" variant="outlined"
        />
      </template>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import SettingsClaudeCode from './SettingsClaudeCode.vue'

const settingsStore = useSettingsStore()

const needsClaudeCode = computed(() =>
  settingsStore.connections.aiConfig.preset === 'hybrid'
  || settingsStore.connections.aiConfig.preset === 'claude-ollama'
)

const presets = [
  {
    value: 'hybrid',
    icon: 'mdi-shuffle-variant',
    title: 'Hybrid',
    description: 'Claude Code for codebase agents, Cloud API for the rest.',
    recommended: true,
  },
  {
    value: 'claude-ollama',
    icon: 'mdi-console-network',
    title: 'Claude + Ollama',
    description: 'Claude Code for codebase agents, Ollama for the rest.',
  },
  {
    value: 'cloud',
    icon: 'mdi-cloud-outline',
    title: 'Cloud API',
    description: 'Use Anthropic or OpenAI for all agents.',
  },
  {
    value: 'local',
    icon: 'mdi-server-outline',
    title: 'Local (Ollama)',
    description: 'Run everything locally. No API keys needed.',
  },
]

const cloudProviders = [
  { title: 'Anthropic', value: 'anthropic' },
  { title: 'OpenAI', value: 'openai' },
]

const activePresetTitle = computed(() => {
  const p = presets.find(p => p.value === settingsStore.connections.aiConfig.preset)
  return p?.title ?? 'AI'
})

const activePresetHint = computed(() => {
  switch (settingsStore.connections.aiConfig.preset) {
    case 'local': return 'All 11 agents will use Ollama running on your machine.'
    case 'cloud': return 'All 11 agents will use the selected cloud provider.'
    case 'hybrid': return 'Codebase agents use Claude Code; other agents use the Cloud API.'
    case 'claude-ollama': return 'Codebase agents use Claude Code; other agents use Ollama locally.'
    default: return ''
  }
})
</script>
