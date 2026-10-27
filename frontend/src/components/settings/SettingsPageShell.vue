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
  <AppPage :title="title" :subtitle="subtitle">
    <template #actions>
      <slot name="header-actions" />
      <v-btn variant="text" prepend-icon="mdi-arrow-left" :to="{ name: 'settings' }">Back to Settings</v-btn>
      <v-btn color="primary" variant="flat" :loading="saving" :disabled="!valid" @click="$emit('save')">Save changes</v-btn>
    </template>

    <AppCallout v-if="error" variant="error">{{ error }}</AppCallout>
    <AppCallout v-if="saveSuccess" variant="success">
      Settings saved.
      <template #actions>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Dismiss" @click="$emit('success-close')" />
      </template>
    </AppCallout>

    <div v-if="loading" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate color="primary" aria-label="Loading settings" />
    </div>
    <div v-else>
      <slot />
    </div>
  </AppPage>
</template>

<script setup lang="ts">
import AppCallout from '@/components/common/AppCallout.vue'
import AppPage from '@/components/common/AppPage.vue'

defineProps<{
  title: string
  subtitle?: string
  loading: boolean
  saving: boolean
  valid: boolean
  error: string | null
  saveSuccess: boolean
}>()

defineEmits<{
  save: []
  'success-close': []
}>()
</script>
