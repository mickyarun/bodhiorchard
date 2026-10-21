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

<!-- Employee record (HR): "Generate password" while they've never set their
     own, "Reset password" once they have. The new one is temporary, shown
     once, and shared by email (HR's mail app), Slack DM or copy. -->
<template>
  <template v-if="login">
    <v-btn variant="tonal" size="small" prepend-icon="mdi-key-variant" @click="open">
      {{ ACTION_LABEL[login.action] }}
    </v-btn>
    <v-dialog v-model="dialog" max-width="480">
      <v-card color="surface" rounded="lg">
        <v-card-title class="pt-5 px-6">{{ ACTION_LABEL[login.action] }}</v-card-title>
        <v-card-text class="px-6">
          <template v-if="!result">
            <p class="text-body-2 mb-3">{{ explainer }}</p>
            <v-checkbox
              v-if="login.slack_linked"
              v-model="sendSlack"
              label="Also send it to them on Slack"
              density="compact"
              hide-details
            />
          </template>
          <template v-else>
            <p class="text-body-2 mb-3">
              Share it with {{ name }} now: it's shown only once. They'll choose their own when
              they sign in.
            </p>
            <v-text-field
              :model-value="result.password"
              label="Temporary password"
              :type="reveal ? 'text' : 'password'"
              readonly
              variant="outlined"
              density="comfortable"
              hide-details
              :append-inner-icon="reveal ? 'mdi-eye-off' : 'mdi-eye'"
              @click:append-inner="reveal = !reveal"
            />
            <div class="d-flex flex-wrap ga-2 mt-4">
              <v-btn variant="tonal" prepend-icon="mdi-email-outline" :href="mailto">Share via email</v-btn>
              <v-btn variant="tonal" prepend-icon="mdi-content-copy" @click="copy">
                {{ copied ? 'Copied' : 'Copy' }}
              </v-btn>
            </div>
            <AppCallout v-if="result.slack_sent" variant="success" class="mt-4">Sent to them on Slack.</AppCallout>
            <AppCallout v-else-if="result.slack_error" variant="warning" class="mt-4">
              {{ result.slack_error }}
            </AppCallout>
          </template>
          <AppCallout v-if="error" variant="error" class="mt-3">{{ error }}</AppCallout>
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="dialog = false">{{ result ? 'Done' : 'Cancel' }}</v-btn>
          <v-btn v-if="!result" color="primary" variant="flat" :loading="busy" @click="submit">
            {{ login.action === 'reset' ? 'Reset' : 'Generate' }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </template>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import { ACTION_LABEL, useEmployeeLogin } from '@/composables/useEmployeeLogin'
import { credentialsMailto } from '@/utils/credentialsMail'

const props = defineProps<{ userId: string; name: string }>()
const { login, result, busy, error, load, issue } = useEmployeeLogin(() => props.userId)
const dialog = ref(false)
const sendSlack = ref(false)
const reveal = ref(false)
const copied = ref(false)

const explainer = computed(() => {
  const first =
    login.value?.action === 'reset'
      ? `${props.name}'s current password stops working straight away.`
      : `${props.name} hasn't set up their own password yet.`
  return (
    `${first} They'll get a temporary one to sign in with and must choose their own. ` +
    "Until they do, they can't approve leave from Slack."
  )
})

const mailto = computed(() =>
  result.value && login.value
    ? credentialsMailto({
        name: props.name,
        email: login.value.email,
        password: result.value.password,
        loginUrl: result.value.login_url,
      })
    : undefined,
)

function open(): void {
  result.value = null
  error.value = ''
  sendSlack.value = false
  reveal.value = false
  copied.value = false
  dialog.value = true
}

async function submit(): Promise<void> {
  await issue(sendSlack.value)
}

async function copy(): Promise<void> {
  if (!result.value) return
  try {
    await navigator.clipboard.writeText(result.value.password)
    copied.value = true
  } catch {
    reveal.value = true // No clipboard (e.g. plain http): show it to copy by hand.
  }
}

onMounted(() => void load())
</script>
