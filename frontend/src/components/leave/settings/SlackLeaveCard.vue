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

<!-- Settings → Leave: the daily who's-out post, how approvers decide from
     Slack, and people's Slack status. Org-wide, above the policy list. -->
<template>
  <v-card color="surface" border rounded="lg" class="pa-6 mb-6">
    <div class="d-flex align-center ga-3 mb-5">
      <v-avatar size="36" color="surface-variant" rounded="lg">
        <v-icon icon="mdi-slack" size="22" />
      </v-avatar>
      <div>
        <div class="text-body-1 font-weight-medium">Slack</div>
        <div class="text-caption text-medium-emphasis">
          A daily post of who's out, and Approve / Reject buttons in approvers' DMs.
        </div>
      </div>
    </div>

    <v-switch
      v-model="digest.settings.value.enabled"
      color="primary"
      label="Post who's out every working day"
      hide-details
      class="mb-4"
    />
    <div class="field-grid">
      <v-text-field
        v-model.trim="digest.settings.value.channel_id"
        label="Channel ID"
        placeholder="C0123ABCD"
        hint="In Slack: channel name → View channel details → ID at the bottom."
        persistent-hint
        v-bind="field"
      />
      <v-text-field
        v-model="digest.settings.value.post_time"
        label="Post at"
        type="time"
        hint="In the default policy's timezone."
        persistent-hint
        v-bind="field"
      />
    </div>
    <p class="text-caption text-medium-emphasis mt-4">
      Names only, never the leave type or reason. People on leave aren't @mentioned.
    </p>

    <AppCallout v-if="digest.error.value" variant="error" class="mt-4">{{ digest.error.value }}</AppCallout>
    <AppCallout v-else-if="message" :variant="messageVariant" class="mt-4">{{ message }}</AppCallout>
    <div class="d-flex flex-wrap ga-2 mt-5">
      <v-btn color="primary" :loading="digest.saving.value" @click="save">Save</v-btn>
      <v-btn variant="tonal" :loading="testing" :disabled="!digest.settings.value.channel_id" @click="test">
        Send test post
      </v-btn>
    </div>

    <v-divider class="my-6" />
    <div class="text-body-2 font-weight-medium mb-1">Approve and reject from Slack</div>
    <p class="text-body-2 text-medium-emphasis mb-2">
      Approvers get each request as a DM with Approve and Reject buttons, no login needed. In your
      Slack app's settings, turn on <strong>Interactivity</strong> and set the Request URL to:
    </p>
    <code class="request-url">{{ requestUrl }}</code>

    <v-divider class="my-6" />
    <SlackStatusSettings />
  </v-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import SlackStatusSettings from '@/components/leave/settings/SlackStatusSettings.vue'
import { useDigestSettings } from '@/composables/useDigestSettings'

const field = { variant: 'outlined', density: 'comfortable', hideDetails: 'auto' } as const
const digest = useDigestSettings()
const message = ref('')
const messageVariant = ref<'success' | 'warning'>('success')
const testing = ref(false)

const requestUrl = computed(() => `${window.location.origin}/api/v1/slack/interactions`)

async function save(): Promise<void> {
  message.value = ''
  if (await digest.save()) {
    messageVariant.value = 'success'
    message.value = 'Saved.'
  }
}

async function test(): Promise<void> {
  testing.value = true
  message.value = await digest.sendTest()
  messageVariant.value = message.value.startsWith('Posted') ? 'success' : 'warning'
  testing.value = false
}

onMounted(() => void digest.load())
</script>

<style scoped>
.field-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px 16px;
  max-width: 720px;
}
@media (max-width: 600px) {
  .field-grid {
    grid-template-columns: 1fr;
  }
}
.request-url {
  display: inline-block;
  padding: 6px 10px;
  border-radius: 6px;
  background: rgb(var(--v-theme-surface-variant));
  font-size: 0.8125rem;
  word-break: break-all;
}
</style>
