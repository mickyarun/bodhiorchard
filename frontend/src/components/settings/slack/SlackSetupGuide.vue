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

<!-- How to create the Slack app: the one-step manifest, then the event
     subscription and scopes to check. -->
<template>
  <v-expansion-panels variant="accordion" flat class="slack-guide">
    <v-expansion-panel>
      <v-expansion-panel-title>Quick setup with the app manifest</v-expansion-panel-title>
      <v-expansion-panel-text>
        <ol class="steps">
          <li>Go to <strong>api.slack.com/apps</strong>, choose <strong>Create New App</strong>, then <strong>From a manifest</strong>.</li>
          <li>Pick your workspace, choose <strong>JSON</strong> and paste the manifest.</li>
          <li>Review it and choose <strong>Create</strong>.</li>
          <li>Choose <strong>Install to Workspace</strong> and copy the <strong>Bot Token</strong> (starts <code>xoxb-</code>).</li>
          <li>Under <strong>Basic Information</strong>, copy the <strong>Signing Secret</strong>.</li>
        </ol>
        <v-btn variant="outlined" size="small" prepend-icon="mdi-content-copy" class="my-2" @click="copy(manifest, 'manifest')">
          {{ copied === 'manifest' ? 'Copied' : 'Copy manifest' }}
        </v-btn>
        <pre class="code">{{ manifest }}</pre>
      </v-expansion-panel-text>
    </v-expansion-panel>
    <v-expansion-panel>
      <v-expansion-panel-title>Event subscriptions and scopes</v-expansion-panel-title>
      <v-expansion-panel-text>
        <ol class="steps">
          <li>In your Slack app, open <strong>Event Subscriptions</strong> and turn <strong>Enable Events</strong> on.</li>
          <li>
            Set the <strong>Request URL</strong> to
            <span class="url-row">
              <code class="code code--inline">{{ eventsUrl }}</code>
              <v-btn
                :icon="copied === 'url' ? 'mdi-check' : 'mdi-content-copy'"
                size="small"
                variant="text"
                aria-label="Copy request URL"
                @click="copy(eventsUrl, 'url')"
              />
            </span>
          </li>
          <li>Under <strong>Subscribe to bot events</strong>, add <code v-for="e in SLACK_BOT_EVENTS" :key="e" class="mr-1">{{ e }}</code></li>
          <li>Under <strong>OAuth and Permissions</strong>, Bot Token Scopes, make sure these are added: <code v-for="sc in SLACK_BOT_SCOPES" :key="sc" class="mr-1">{{ sc }}</code></li>
          <li>Choose <strong>Save Changes</strong> and reinstall the app when Slack asks.</li>
        </ol>
        <p class="hint">Presence (online or away) comes from the <code>users:read</code> scope, so it needs no extra event.</p>
      </v-expansion-panel-text>
    </v-expansion-panel>
  </v-expansion-panels>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { copyText } from '@/utils/clipboard'
import { SLACK_BOT_EVENTS, SLACK_BOT_SCOPES, slackEventsUrl, slackManifest } from '@/utils/slackManifest'

const COPIED_MS = 2000

const manifest = slackManifest()
const eventsUrl = slackEventsUrl(window.location.origin)
const copied = ref<'manifest' | 'url' | null>(null)

async function copy(text: string, what: 'manifest' | 'url'): Promise<void> {
  if (!(await copyText(text))) return
  copied.value = what
  setTimeout(() => { copied.value = null }, COPIED_MS)
}
</script>

<style scoped>
.slack-guide {
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 10px;
  overflow: hidden;
}
.slack-guide :deep(.v-expansion-panel-title) {
  font-size: 14px;
  font-weight: 500;
}
.steps {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  line-height: 1.7;
  color: rgb(var(--v-theme-ink-2));
}
.code {
  margin: 0;
  padding: 10px 12px;
  max-height: 160px;
  overflow: auto;
  border-radius: 8px;
  font-family: var(--font-mono);
  font-size: 12px;
  background: rgb(var(--v-theme-background));
  color: rgb(var(--v-theme-ink-2));
}
.code--inline {
  display: inline-block;
  padding: 4px 8px;
  max-height: none;
  overflow-wrap: anywhere;
}
.url-row {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
}
.hint {
  margin: 8px 0 0;
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
