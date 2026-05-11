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

<template>
  <div class="notification-preferences">
    <h2>Notification Settings</h2>
    <form @submit.prevent="savePreferences">
      <label>
        <input v-model="emailEnabled" type="checkbox" />
        Email notifications
      </label>
      <label>
        <input v-model="pushEnabled" type="checkbox" />
        Push notifications
      </label>
      <div class="form-group">
        <label for="digest">Digest frequency</label>
        <select id="digest" v-model="digestFrequency">
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
          <option value="none">None</option>
        </select>
      </div>
      <button type="submit">Save</button>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import api from '@/services/api'

const emailEnabled = ref(true)
const pushEnabled = ref(true)
const digestFrequency = ref('daily')

async function savePreferences() {
  await api.put('/notifications/preferences', {
    email_enabled: emailEnabled.value,
    push_enabled: pushEnabled.value,
    digest_frequency: digestFrequency.value,
  })
}
</script>
