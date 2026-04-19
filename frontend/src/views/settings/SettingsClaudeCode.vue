<template>
  <v-card class="pa-6 settings-card" color="surface">
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
        color="success" variant="flat" size="small"
        prepend-icon="mdi-check-circle-outline"
      >
        Connected
      </v-chip>
      <v-chip
        v-else-if="claudeStatus === 'failed'"
        color="error" variant="flat" size="small"
        prepend-icon="mdi-alert-circle-outline"
      >
        Not Available
      </v-chip>
    </div>

    <div class="mt-4">
      <v-btn
        color="primary"
        variant="tonal"
        prepend-icon="mdi-connection"
        :loading="claudeStatus === 'checking'"
        @click="checkClaudeCode"
      >
        {{ claudeStatus === 'idle' ? 'Test Connection' : 'Retest' }}
      </v-btn>

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
</template>

<script setup lang="ts">
import { ref } from 'vue'
import api from '@/services/api'

const claudeStatus = ref<'idle' | 'checking' | 'passed' | 'failed'>('idle')
const claudeError = ref('')
const claudeVersion = ref('')

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
</script>
