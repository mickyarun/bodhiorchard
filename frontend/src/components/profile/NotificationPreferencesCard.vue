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

<!--
  Self-service Slack notification preferences. Lists every category the
  backend registry exposes, grouped, with a per-category switch. Each toggle
  saves on its own (optimistic + revert on error) so there is no explicit
  Save button — turning a switch off muts that category's Slack DMs for the
  signed-in member only.
-->
<template>
  <v-card color="surface" border class="pa-6">
    <div class="d-flex align-center ga-3 mb-4">
      <v-avatar size="36" color="surface-variant" rounded="lg">
        <v-icon icon="mdi-bell-cog-outline" size="22" />
      </v-avatar>
      <div>
        <div class="text-body-1 font-weight-medium">Notifications</div>
        <div class="text-caption text-medium-emphasis">
          Choose which Slack messages you want to receive
        </div>
      </div>
    </div>

    <AppCallout variant="info" icon="mdi-slack" class="mb-4">
      These control the direct messages our Slack bot sends you. Turning one off
      affects only your account — your teammates keep getting them.
    </AppCallout>

    <div v-if="loading" class="d-flex justify-center py-6">
      <v-progress-circular indeterminate color="primary" size="28" />
    </div>

    <template v-else>
      <div v-for="group in groupedItems" :key="group.name" class="mb-4">
        <div class="text-overline text-medium-emphasis mb-1">{{ group.name }}</div>
        <div
          v-for="item in group.items"
          :key="item.key"
          class="d-flex align-center justify-space-between py-2"
        >
          <div class="pr-4">
            <div class="text-body-2 font-weight-medium">{{ item.label }}</div>
            <div class="text-caption text-medium-emphasis">{{ item.description }}</div>
          </div>
          <v-switch
            :model-value="item.enabled"
            color="primary"
            hide-details
            density="compact"
            inset
            :loading="savingKey === item.key"
            :disabled="savingKey !== null"
            @update:model-value="onToggle(item, $event)"
          />
        </div>
      </div>

      <AppCallout v-if="error" variant="warning" icon="mdi-alert-outline">
        {{ error }}
      </AppCallout>
    </template>
  </v-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import api from '@/services/api'
import AppCallout from '@/components/common/AppCallout.vue'
import type { NotificationPreferenceItem } from '@/types'

const items = ref<NotificationPreferenceItem[]>([])
const loading = ref(true)
const savingKey = ref<string | null>(null)
const error = ref('')

// Bucket categories under their backend-provided group heading, preserving
// the registry's order. The backend is the single source of order and copy;
// the UI only renders what it sends.
const groupedItems = computed(() => {
  const buckets: { name: string; items: NotificationPreferenceItem[] }[] = []
  for (const item of items.value) {
    let bucket = buckets.find(b => b.name === item.group)
    if (!bucket) {
      bucket = { name: item.group, items: [] }
      buckets.push(bucket)
    }
    bucket.items.push(item)
  }
  return buckets
})

async function load(): Promise<void> {
  loading.value = true
  try {
    const { data } = await api.get<{ items: NotificationPreferenceItem[] }>(
      '/v1/me/notification-preferences',
    )
    items.value = data.items
  } catch {
    error.value = 'Could not load your notification settings. Try refreshing.'
  } finally {
    loading.value = false
  }
}

async function onToggle(item: NotificationPreferenceItem, value: boolean | null): Promise<void> {
  const enabled = value ?? false
  const previous = item.enabled
  item.enabled = enabled // optimistic
  savingKey.value = item.key
  error.value = ''
  try {
    await api.patch('/v1/me/notification-preferences', {
      preferences: { [item.key]: enabled },
    })
  } catch {
    item.enabled = previous // revert
    error.value = 'Could not save that change. Please try again.'
  } finally {
    savingKey.value = null
  }
}

onMounted(load)
</script>
