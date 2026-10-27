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

<!-- The workspace MCP token for Claude Code: generate or replace it (it
     is shown once), then set it as an environment variable. Repository
     scans already write .mcp.json; the token is what activates it. -->
<template>
  <div class="mcp-panel">
    <div class="mcp-panel__row">
      <span class="mcp-panel__text">
        {{ hasToken ? 'A workspace token is set. Replacing it stops the old one working.' : 'No workspace token yet.' }}
      </span>
      <v-btn
        :color="hasToken ? undefined : 'primary'"
        :variant="hasToken ? 'outlined' : 'flat'"
        :loading="generating"
        @click="hasToken ? (confirmOpen = true) : generate()"
      >
        {{ hasToken ? 'Replace token' : 'Generate token' }}
      </v-btn>
    </div>

    <AppCallout v-if="error" variant="error">{{ error }}</AppCallout>
    <AppCallout v-if="newToken" variant="warning" title="Copy the token now. It is not shown again.">
      <div class="mcp-panel__token">
        <PasswordField :model-value="newToken" label="Workspace MCP token" variant="outlined" density="compact" readonly hide-details />
        <v-btn
          :icon="copied === 'token' ? 'mdi-check' : 'mdi-content-copy'"
          :aria-label="copied === 'token' ? 'Copied' : 'Copy token'"
          variant="text"
          @click="copy(newToken, 'token')"
        />
      </div>
    </AppCallout>

    <p class="mcp-panel__text">
      Set it as a lasting environment variable, then restart your terminal and Claude Code. The token stays
      hidden here; copying the line fills it in when you have just generated one.
    </p>
    <div class="mcp-panel__snippet">
      <pre>{{ exportLine('') }}</pre>
      <v-btn
        :icon="copied === 'line' ? 'mdi-check' : 'mdi-content-copy'"
        :aria-label="copied === 'line' ? 'Copied' : 'Copy the export line'"
        size="small"
        variant="text"
        @click="copy(exportLine(newToken), 'line')"
      />
    </div>
    <v-expansion-panels variant="accordion" flat class="mcp-panel__shells">
      <v-expansion-panel v-for="snippet in shellSnippets('')" :key="snippet.id">
        <v-expansion-panel-title>
          <v-icon :icon="snippet.icon" size="16" class="mr-2" />{{ snippet.label }}
        </v-expansion-panel-title>
        <v-expansion-panel-text><pre class="mcp-panel__code">{{ snippet.code }}</pre></v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>
    <ConfirmDialog
      v-model="confirmOpen"
      title="Replace the workspace token?"
      message="The current token stops working straight away. Anyone using it needs the new one."
      confirm-label="Replace token"
      tone="warning"
      @confirm="generate"
    />
    <p class="mcp-panel__text">
      Each person can also make their own token on <router-link to="/settings/mcp-connect">MCP connect</router-link>.
    </p>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import PasswordField from '@/components/common/PasswordField.vue'
import ConfirmDialog from '@/components/settings/code/ConfirmDialog.vue'
import api from '@/services/api'
import { copyText } from '@/utils/clipboard'
import { exportLine, shellSnippets } from '@/utils/mcpEnvSnippets'

const COPIED_MS = 2000

const hasToken = defineModel<boolean>('hasToken', { required: true })

const newToken = ref('')
const generating = ref(false)
const error = ref('')
const copied = ref<'token' | 'line' | null>(null)
const confirmOpen = ref(false)

onMounted(async () => {
  try {
    const { data } = await api.get('/v1/settings/mcp-token/status')
    hasToken.value = data.has_token
  } catch {
    // The status only shapes the wording; the panel still works without it.
  }
})

async function generate(): Promise<void> {
  generating.value = true
  error.value = ''
  try {
    const { data } = await api.post('/v1/settings/mcp-token')
    newToken.value = data.mcp_token
    hasToken.value = true
  } catch {
    error.value = 'Could not generate the MCP token.'
  } finally {
    generating.value = false
  }
}

async function copy(text: string, what: 'token' | 'line'): Promise<void> {
  if (!(await copyText(text))) {
    error.value = 'Could not copy. Copy it by hand instead.'
    return
  }
  copied.value = what
  setTimeout(() => { copied.value = null }, COPIED_MS)
}
</script>

<style scoped>
.mcp-panel__shells {
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 10px;
  overflow: hidden;
}
.mcp-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.mcp-panel__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.mcp-panel__text {
  margin: 0;
  font-size: 13px;
  color: rgb(var(--v-theme-ink-2));
}
.mcp-panel__text a {
  color: var(--color-accent-text);
}
.mcp-panel__token {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}
.mcp-panel__snippet {
  display: flex;
  align-items: flex-start;
  gap: 4px;
  padding: 6px 6px 6px 12px;
  border-radius: 8px;
  background: rgb(var(--v-theme-background));
}
.mcp-panel__snippet pre,
.mcp-panel__code {
  flex: 1 1 auto;
  min-width: 0;
  margin: 0;
  padding-top: 6px;
  font-family: var(--font-mono);
  font-size: 12px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: rgb(var(--v-theme-ink-2));
}
</style>
