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

<!-- Settings → Leave → Slack card: let people show WFH / leave as their
     Slack status. Needs the Slack app's OAuth client; each person then
     connects once from their Leave page. -->
<template>
  <div class="text-body-2 font-weight-medium mb-1">Slack status on WFH and leave days</div>
  <p class="text-body-2 text-medium-emphasis mb-2">
    Slack only lets each person allow status changes for themselves, so once this is on, everyone
    gets a <strong>Connect Slack</strong> button on their Leave page. In your Slack app's
    <strong>OAuth &amp; Permissions</strong>, add this Redirect URL and the user scopes
    <code>users.profile:read</code> and <code>users.profile:write</code>. Leave token rotation
    off. Switching this off takes the status off everyone straight away.
  </p>
  <code class="request-url mb-4">{{ form.settings.value.redirect_url }}</code>

  <v-switch
    v-model="form.settings.value.enabled"
    color="primary"
    label="Offer Slack status to everyone"
    hide-details
    class="mt-4 mb-4"
  />
  <div class="field-grid">
    <v-text-field
      v-model.trim="form.settings.value.client_id"
      label="Client ID"
      hint="Slack app → Basic Information → App Credentials."
      persistent-hint
      v-bind="field"
    />
    <v-text-field
      v-model="secret"
      label="Client secret"
      type="password"
      autocomplete="off"
      :hint="form.settings.value.has_client_secret ? 'Saved. Enter a new one to replace it.' : 'Kept encrypted.'"
      persistent-hint
      v-bind="field"
    />
  </div>
  <AppCallout v-if="form.error.value" variant="error" class="mt-4">{{ form.error.value }}</AppCallout>
  <AppCallout v-else-if="saved" variant="success" class="mt-4">Saved.</AppCallout>
  <v-btn color="primary" class="mt-5" :loading="form.saving.value" @click="save">Save</v-btn>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import { useSlackStatusSettings } from '@/composables/useSlackStatus'

const field = { variant: 'outlined', density: 'comfortable', hideDetails: 'auto' } as const
const form = useSlackStatusSettings()
const secret = ref('')
const saved = ref(false)

async function save(): Promise<void> {
  saved.value = false
  if (await form.save(secret.value || null)) {
    secret.value = ''
    saved.value = true
  }
}

onMounted(() => void form.load())
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
