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
  <div class="notification-bell" @click="togglePanel">
    <span class="icon">🔔</span>
    <span v-if="unreadCount > 0" class="badge">{{ unreadCount }}</span>

    <div v-if="showPanel" class="notification-panel">
      <div class="panel-header">
        <h3>Notifications</h3>
        <button @click.stop="markAllRead">Mark all read</button>
      </div>
      <div v-for="n in notifications" :key="n.id" class="notification-item" :class="{ unread: !n.is_read }">
        <p class="title">{{ n.title }}</p>
        <p class="type">{{ n.type }}</p>
      </div>
      <p v-if="notifications.length === 0" class="empty">No notifications</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import api from '@/services/api'

interface Notification {
  id: number
  type: string
  title: string
  is_read: boolean
}

const notifications = ref<Notification[]>([])
const showPanel = ref(false)

const unreadCount = computed(() => notifications.value.filter(n => !n.is_read).length)

onMounted(async () => {
  const { data } = await api.get('/notifications')
  notifications.value = data
})

function togglePanel() {
  showPanel.value = !showPanel.value
}

async function markAllRead() {
  await api.post('/notifications/read-all')
  notifications.value.forEach(n => { n.is_read = true })
}
</script>
