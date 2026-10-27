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

<!-- Generate a temporary password for a member and share it by Slack DM
     (generated and sent server-side) or by email. The password stays
     masked until revealed. -->
<template>
  <v-dialog v-model="open" max-width="500" persistent>
    <v-card>
      <v-card-title class="d-flex align-center justify-space-between">
        <span>Set password</span>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="open = false" />
      </v-card-title>
      <v-card-text>
        <template v-if="!password">
          <p class="mb-4">
            Generate a temporary password for <strong>{{ member?.name }}</strong>. They change it the first
            time they sign in.
          </p>
          <v-btn color="primary" variant="flat" prepend-icon="mdi-key-plus" :loading="generating" @click="generate">
            Generate password
          </v-btn>
        </template>

        <template v-else>
          <AppCallout variant="success" class="mb-4">
            Password generated. Share it with {{ member?.name }} below.
          </AppCallout>
          <div class="d-flex align-center ga-2 mb-4">
            <PasswordField :model-value="password" label="Temporary password" variant="outlined" density="compact" readonly hide-details />
            <v-btn
              :icon="copied ? 'mdi-check' : 'mdi-content-copy'"
              :aria-label="copied ? 'Copied' : 'Copy password'"
              variant="outlined"
              @click="copy"
            />
          </div>
          <div class="text-subtitle-2 mb-2">Share it</div>
          <div class="d-flex flex-column ga-2">
            <v-btn
              v-if="slackEnabled && member?.slackId"
              variant="outlined"
              prepend-icon="mdi-slack"
              :loading="sendingSlack"
              :disabled="slackSent"
              @click="sendViaSlack"
            >
              {{ slackSent ? 'Sent by Slack DM' : 'Send by Slack DM' }}
            </v-btn>
            <p v-else-if="slackEnabled" class="text-caption text-medium-emphasis mb-0">
              Slack DM is unavailable: this member has no linked Slack account.
            </p>
            <v-btn variant="outlined" prepend-icon="mdi-email-outline" :href="mailtoLink">Share by email</v-btn>
          </div>
        </template>

        <AppCallout v-if="sendError" variant="error" class="mt-3">{{ sendError }}</AppCallout>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="open = false">Close</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import PasswordField from '@/components/common/PasswordField.vue'
import { useMembersStore, type Member } from '@/stores/members'
import { useSettingsStore } from '@/stores/settings'
import { copyText } from '@/utils/clipboard'
import { credentialsMailto } from '@/utils/credentialsMail'

const COPIED_MS = 2000

const props = defineProps<{ member: Member | null }>()
const open = defineModel<boolean>({ required: true })
const store = useMembersStore()
const settingsStore = useSettingsStore()

const password = ref('')
const loginUrl = ref('')
const generating = ref(false)
const copied = ref(false)
const sendingSlack = ref(false)
const slackSent = ref(false)
const sendError = ref('')

const slackEnabled = computed(() => !!settingsStore.connections.slack?.enabled)

const mailtoLink = computed(() => {
  if (!props.member || !password.value) return ''
  return credentialsMailto({
    name: props.member.name,
    email: props.member.email,
    password: password.value,
    loginUrl: loginUrl.value,
  })
})

// Each opening starts clean, and closing drops the password from memory.
watch(open, () => {
  password.value = ''
  loginUrl.value = ''
  copied.value = false
  slackSent.value = false
  sendError.value = ''
})

async function generate(): Promise<void> {
  if (!props.member) return
  generating.value = true
  sendError.value = ''
  const result = await store.setPassword(props.member.id)
  generating.value = false
  if (result) {
    password.value = result.password
    loginUrl.value = result.loginUrl
  } else {
    sendError.value = store.error || 'Could not generate a password.'
  }
}

async function copy(): Promise<void> {
  if (await copyText(password.value)) {
    copied.value = true
    setTimeout(() => { copied.value = false }, COPIED_MS)
  } else {
    sendError.value = 'Could not copy. Reveal the password and copy it by hand.'
  }
}

async function sendViaSlack(): Promise<void> {
  if (!props.member) return
  sendingSlack.value = true
  sendError.value = ''
  // Generate and send in one server-side call so the password never round-trips.
  const result = await store.setPassword(props.member.id, 'slack')
  sendingSlack.value = false
  if (!result) {
    sendError.value = store.error || 'Could not set the password.'
    return
  }
  password.value = result.password
  loginUrl.value = result.loginUrl
  if (result.slackSent) slackSent.value = true
  else sendError.value = result.slackError || 'Could not send by Slack.'
}
</script>
