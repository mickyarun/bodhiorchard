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

<!-- Leave home: offer to show WFH / leave as the member's Slack status, and
     finish when Slack sends them back (#slackCode=…&slackState=…, or
     ?slackStatus=… if they cancelled). Renders nothing when HR hasn't set it up. -->
<template>
  <AppCallout v-if="outcome" :variant="outcome.ok ? 'success' : 'warning'" class="mb-4">
    {{ outcome.text }}
  </AppCallout>
  <AppCallout v-if="status.error.value" variant="error" class="mb-4">{{ status.error.value }}</AppCallout>
  <AppCallout v-if="mine?.available && !mine.connected" variant="info" class="mb-6">
    Show "Working from home" and "On leave" as your Slack status on those days. It's cleared
    automatically, and never says the type of leave.
    <template v-if="!mine.linked">
      Sign in to the Slack account that uses the same email as your profile here.
    </template>
    <template #actions>
      <v-btn size="small" variant="tonal" color="primary" :loading="status.busy.value" @click="status.connect">
        Connect Slack
      </v-btn>
    </template>
  </AppCallout>
  <div v-else-if="mine?.connected" class="d-flex align-center ga-2 mb-6 text-body-2 text-medium-emphasis">
    <v-icon icon="mdi-slack" size="18" />
    {{ mine.available ? 'Your Slack status shows WFH and leave days.' : 'Slack status is switched off for your team.' }}
    <v-btn size="small" variant="text" :loading="status.busy.value" @click="status.disconnect">Turn off</v-btn>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppCallout from '@/components/common/AppCallout.vue'
import { connectOutcome, useMySlackStatus } from '@/composables/useSlackStatus'

const route = useRoute()
const router = useRouter()
const status = useMySlackStatus()
const mine = computed(() => status.mine.value)
const outcome = ref(connectOutcome(queryText('slackStatus')))

function queryText(key: string): string | null {
  const value = route.query[key]
  return typeof value === 'string' ? value : null
}

onMounted(async () => {
  const handed = new URLSearchParams(route.hash.slice(1))
  const code = handed.get('slackCode')
  const state = handed.get('slackState')
  // Only once it's finished: if the session ran out on the way, the sign-in
  // redirect remembers this URL, code included, to finish after login.
  if (code && state) outcome.value = connectOutcome(await status.finish(code, state))
  if (outcome.value) {
    // Shown once, and the code is single-use: take it out of the URL.
    const { slackStatus: _s, ...rest } = route.query
    void router.replace({ query: rest, hash: '' })
  }
  await status.load()
})
</script>
