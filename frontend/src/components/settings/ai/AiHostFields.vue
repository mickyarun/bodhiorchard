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

<!-- Settings for a provider that runs on the org's own server: its
     address, the tool-capable model to use and whether it reasons first. -->
<template>
  <div class="host-fields">
    <div v-if="caps.requires_base_url">
      <v-text-field
        v-model="baseUrl"
        label="Server address"
        :placeholder="caps.default_base_url ?? ''"
        persistent-placeholder
        variant="outlined"
        density="compact"
        autocomplete="off"
        hide-details
      />
      <p class="host-fields__hint">
        Leave blank for <code>{{ caps.default_base_url }}</code>. A shared or hosted server works too: include any
        path prefix it serves Ollama under, and pick token sign-in below if it needs a credential.
        <template v-if="deploymentMode === 'docker'">
          This backend runs in Docker, so <code>localhost</code> is the container. Use
          <code>http://host.docker.internal:11434</code> for a server on this machine.
        </template>
      </p>
    </div>
    <div v-if="caps.dynamic_models">
      <v-select
        v-model="model"
        :items="caps.models"
        item-title="label"
        item-value="id"
        label="Model"
        variant="outlined"
        density="compact"
        hide-details
        no-data-text="No tool-capable models found"
      />
      <p class="host-fields__hint">
        <template v-if="caps.models.length">Read from your server. Only models that can call tools are listed, because agents need them.</template>
        <template v-else>None found. Check the server address, then install one, for example <code>ollama pull qwen3</code>.</template>
      </p>
    </div>
    <div v-if="caps.supports_thinking">
      <div class="host-fields__label">Reasoning</div>
      <AppPillToggle v-model="thinking" :options="THINKING_OPTIONS" aria-label="Reasoning" />
      <p class="host-fields__hint">
        Reasoning before answering roughly doubles response time and made no measurable difference on these tasks,
        so Off is recommended.
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import type { ProviderCaps } from '@/constants/aiProviders'

const THINKING_OPTIONS: { label: string; value: 'on' | 'off' }[] = [
  { label: 'Off (faster)', value: 'off' },
  { label: 'On (slower)', value: 'on' },
]

defineProps<{ caps: ProviderCaps; deploymentMode: string }>()
const baseUrl = defineModel<string>('baseUrl', { required: true })
const model = defineModel<string>('model', { required: true })
const thinking = defineModel<'on' | 'off'>('thinking', { required: true })
</script>

<style scoped>
.host-fields {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.host-fields__label {
  margin-bottom: 6px;
  font-size: 13px;
  font-weight: 500;
}
.host-fields__hint {
  margin: 6px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
