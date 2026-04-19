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
