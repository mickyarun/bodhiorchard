<template>
  <div class="d-flex flex-column align-center">
    <v-icon icon="mdi-robot-outline" size="48" color="primary" class="mb-4" />
    <h2 class="text-h5 font-weight-bold mb-2">AI Engine</h2>
    <p class="text-body-2 text-medium-emphasis mb-6" style="max-width: 480px; text-align: center;">
      Bodhigrove uses Claude Code to analyze your codebase.
      Verify it's installed and working.
    </p>

    <!-- Claude Code — active -->
    <v-card class="pa-5 card-border-dark mb-4 w-100" color="surface" style="max-width: 560px;">
      <div class="d-flex align-center ga-3 mb-4">
        <v-avatar size="40" color="primary" rounded="lg">
          <v-icon icon="mdi-console" size="22" color="white" />
        </v-avatar>
        <div class="flex-grow-1">
          <div class="text-body-1 font-weight-medium">Claude Code</div>
          <div class="text-caption text-medium-emphasis">
            Codebase-aware AI agent running locally
          </div>
        </div>
        <v-chip color="success" variant="tonal" size="small">Active</v-chip>
      </div>

      <v-btn
        :color="testStatus === 'passed' ? 'success' : 'primary'"
        :loading="testStatus === 'checking'"
        :prepend-icon="testStatus === 'passed' ? 'mdi-check-circle' : 'mdi-play-circle-outline'"
        variant="tonal"
        block
        @click="testConnection"
      >
        {{ testStatus === 'passed' ? 'Connected' : testStatus === 'failed' ? 'Retry Connection Test' : 'Test Connection' }}
      </v-btn>

      <div v-if="testStatus === 'passed'" class="mt-3">
        <v-alert type="success" variant="tonal" density="compact">
          Claude Code {{ claudeVersion }} is ready.
        </v-alert>
      </div>
      <div v-if="testStatus === 'failed'" class="mt-3">
        <v-alert type="error" variant="tonal" density="compact">
          {{ testError }}
        </v-alert>
        <div class="text-caption text-medium-emphasis mt-2">
          Install Claude Code:
          <code class="text-primary">curl -fsSL https://claude.ai/install.sh | bash</code>
        </div>
      </div>
    </v-card>

    <!-- Coming Soon options -->
    <div class="w-100" style="max-width: 560px;">
      <div class="text-caption text-medium-emphasis mb-2 ml-1">More AI engines coming soon</div>
      <div class="d-flex flex-wrap ga-2">
        <v-chip variant="outlined" color="grey" prepend-icon="mdi-cloud-outline" disabled>
          Cloud API
          <template #append>
            <v-chip size="x-small" variant="tonal" color="grey" class="ml-1">Soon</v-chip>
          </template>
        </v-chip>
        <v-chip variant="outlined" color="grey" prepend-icon="mdi-server-outline" disabled>
          Ollama
          <template #append>
            <v-chip size="x-small" variant="tonal" color="grey" class="ml-1">Soon</v-chip>
          </template>
        </v-chip>
        <v-chip variant="outlined" color="grey" prepend-icon="mdi-code-braces" disabled>
          Codex
          <template #append>
            <v-chip size="x-small" variant="tonal" color="grey" class="ml-1">Soon</v-chip>
          </template>
        </v-chip>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import api from '@/services/api'

const testStatus = ref<'idle' | 'checking' | 'passed' | 'failed'>('idle')
const claudeVersion = ref('')
const testError = ref('')

async function testConnection(): Promise<void> {
  testStatus.value = 'checking'
  testError.value = ''
  try {
    const { data } = await api.get('/setup/check-claude')
    if (data.test_passed) {
      testStatus.value = 'passed'
      claudeVersion.value = data.version || ''
    } else {
      testStatus.value = 'failed'
      testError.value = data.error || 'Claude Code test failed. Is it installed?'
    }
  } catch {
    testStatus.value = 'failed'
    testError.value = 'Could not reach the server to test Claude Code.'
  }
}
</script>
