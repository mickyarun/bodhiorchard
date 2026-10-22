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

<!-- Settings → Leave: approved leave as "Out of office" and WFH as a "Home"
     working location on each person's own Google Calendar. Org-wide. -->
<template>
  <v-card color="surface" border rounded="lg" class="pa-6 mb-6">
    <div class="d-flex align-center ga-3 mb-5">
      <v-avatar size="36" color="surface-variant" rounded="lg">
        <v-icon icon="mdi-calendar-sync" size="22" />
      </v-avatar>
      <div>
        <div class="text-body-1 font-weight-medium">Google Calendar</div>
        <div class="text-caption text-medium-emphasis">
          Approved leave shows as Out of office and WFH as working from home, on each person's own calendar.
        </div>
      </div>
    </div>

    <v-switch
      v-model="sync.settings.value.enabled"
      color="primary"
      label="Put approved leave and WFH on Google Calendar"
      hide-details
      class="mb-2"
    />
    <v-switch
      v-model="sync.settings.value.decline_meetings"
      color="primary"
      label="Decline new meetings during leave"
      hide-details
      class="mb-4"
    />
    <div class="field-grid">
      <v-text-field
        v-model="sync.settings.value.decline_message"
        label="Decline message"
        :disabled="!sync.settings.value.decline_meetings"
        v-bind="field"
      />
      <v-text-field
        v-model="sync.settings.value.midday"
        label="Half days split at"
        type="time"
        hint="In each person's policy timezone."
        persistent-hint
        v-bind="field"
      />
      <v-file-input
        v-model="keyFile"
        label="Service account key (JSON)"
        accept="application/json,.json"
        prepend-icon=""
        prepend-inner-icon="mdi-key-outline"
        :hint="keyHint"
        persistent-hint
        v-bind="field"
      />
    </div>
    <p class="text-caption text-medium-emphasis mt-4">
      Events say "Out of office" or "Home", never the leave type or reason. Cancelled or rejected
      requests are taken off again, and switching sync off takes upcoming events off too. On
      Workspace editions without working location (Business Starter), WFH shows as an all-day
      "Working from home" entry instead.
    </p>

    <AppCallout v-if="sync.error.value" variant="error" class="mt-4">{{ sync.error.value }}</AppCallout>
    <AppCallout v-else-if="message" :variant="messageVariant" class="mt-4">{{ message }}</AppCallout>
    <div class="d-flex flex-wrap ga-2 mt-5">
      <v-btn color="primary" :loading="sync.saving.value" @click="save">Save</v-btn>
      <v-btn
        variant="tonal"
        :loading="testing"
        :disabled="!sync.settings.value.service_account_email"
        @click="test"
      >
        Test with my calendar
      </v-btn>
    </div>

    <v-divider class="my-6" />
    <div class="text-body-2 font-weight-medium mb-1">Set up once, in Google</div>
    <ol class="text-body-2 text-medium-emphasis setup-steps">
      <li>In Google Cloud, enable the Calendar API and create a service account. Download a JSON key.</li>
      <li>
        In the Workspace Admin console → Security → API controls → Domain-wide delegation, add the
        service account's client ID with the scope <code>{{ scope }}</code>.
      </li>
      <li>Upload the key here, switch sync on and save. Upcoming approved leave is added straight away.</li>
    </ol>
  </v-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import { calendarTestMessage, useCalendarSync } from '@/composables/useCalendarSync'

const field = { variant: 'outlined', density: 'comfortable', hideDetails: 'auto' } as const
const scope = 'https://www.googleapis.com/auth/calendar.events'
const sync = useCalendarSync()
const keyFile = ref<File | null>(null)
const message = ref('')
const messageVariant = ref<'success' | 'warning'>('success')
const testing = ref(false)

const keyHint = computed(() =>
  sync.settings.value.service_account_email
    ? `Saved: ${sync.settings.value.service_account_email}. Upload a new key to replace it.`
    : 'Kept encrypted on the server and never shown again.',
)

async function save(): Promise<void> {
  message.value = ''
  const key = keyFile.value ? await keyFile.value.text() : null
  if (await sync.save(key)) {
    keyFile.value = null
    messageVariant.value = 'success'
    message.value = 'Saved.'
  }
}

async function test(): Promise<void> {
  testing.value = true
  const result = await sync.test()
  message.value = typeof result === 'string' ? result : calendarTestMessage(result)
  messageVariant.value = typeof result !== 'string' && result.ok ? 'success' : 'warning'
  testing.value = false
}

onMounted(() => void sync.load())
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
.setup-steps {
  padding-left: 20px;
  display: grid;
  gap: 4px;
}
</style>
