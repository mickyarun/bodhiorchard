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

<!-- Slack settings inside the Integrations card: the bot credentials
     (masked, kept when left unchanged), the app setup guide and member
     sync. Edits stay local until Save, so another card's save never sends
     half-typed Slack secrets. -->
<template>
  <div class="slack-panel">
    <AppCallout v-if="error" variant="error">{{ error }}</AppCallout>
    <AppCallout v-if="slack.connected" variant="warning" eyebrow="Reinstall required" icon="mdi-refresh-alert">
      The bot now needs the <code>im:write</code> scope to send race invites and member sign-in details as
      direct messages. Reinstall the Slack app to grant it; invites keep arriving in the app meanwhile.
    </AppCallout>

    <div class="slack-panel__fields">
      <PasswordField
        v-model="draft.botToken"
        label="Bot token"
        density="compact"
        variant="outlined"
        autocomplete="off"
        hint="Starts xoxb-. Leave unchanged to keep the saved token."
        persistent-hint
      />
      <PasswordField
        v-model="draft.signingSecret"
        label="Signing secret"
        density="compact"
        variant="outlined"
        autocomplete="off"
        hint="Leave unchanged to keep the saved secret."
        persistent-hint
      />
      <v-text-field
        v-model="draft.teamId"
        label="Workspace team ID"
        density="compact"
        variant="outlined"
        hint="Read from the bot token. Change it only if that is wrong."
        persistent-hint
      />
    </div>
    <div class="slack-panel__save">
      <v-btn color="primary" variant="flat" :loading="saving" @click="save">Save Slack settings</v-btn>
    </div>

    <SlackSetupGuide />
    <SlackMemberSync v-if="slack.connected" />
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import PasswordField from '@/components/common/PasswordField.vue'
import SlackMemberSync from '@/components/settings/slack/SlackMemberSync.vue'
import SlackSetupGuide from '@/components/settings/slack/SlackSetupGuide.vue'
import { useSettingsStore } from '@/stores/settings'

const settingsStore = useSettingsStore()
const slack = computed(() => settingsStore.connections.slack)

const draft = reactive({ botToken: '', signingSecret: '', teamId: '' })
const saving = ref(false)
const error = ref('')

// Reload the draft whenever the saved values change (load, any save).
watch(
  slack,
  s => Object.assign(draft, { botToken: s.botToken, signingSecret: s.signingSecret, teamId: s.teamId }),
  { immediate: true },
)

async function save(): Promise<void> {
  saving.value = true
  error.value = ''
  Object.assign(settingsStore.connections.slack, draft)
  const ok = await settingsStore.saveConnections()
  // The store error is shown here, not by whichever card watches it.
  if (!ok) {
    error.value = settingsStore.error ?? 'Could not save the Slack settings.'
    settingsStore.error = null
  }
  saving.value = false
}
</script>

<style scoped>
.slack-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.slack-panel__fields {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr));
  gap: 12px;
}
.slack-panel__save {
  display: flex;
  justify-content: flex-end;
}
</style>
