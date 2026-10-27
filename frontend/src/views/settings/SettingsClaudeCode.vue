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

<!-- AI provider settings inside the Integrations card: which agent runs
     codebase-aware work, how it signs in, and a connection test. Saves on
     its own (only when something changed) and reports the test result, a
     one-line summary of the saved choice and whether there are edits. -->
<template>
  <div class="ai-panel">
    <p v-if="ai.deploymentMode.value" class="ai-panel__mode">
      Deployment: {{ ai.deploymentMode.value === 'docker' ? 'Full Docker' : 'Hybrid (host login available)' }}
    </p>

    <ChoiceTiles
      :model-value="ai.provider.value"
      :options="providerTiles(ai.providers.value)"
      label="AI provider"
      @update:model-value="ai.selectProvider"
    />

    <!-- Said before the settings, not after a failed run: a provider without
         file access answers confidently about files it never read. -->
    <AppCallout
      v-if="limitations.length"
      variant="warning"
      eyebrow="Feature limits"
      :title="`Not available with ${providerTitle(ai.provider.value)}`"
    >
      This provider reaches your code through the indexed call graph rather than the files, so features that
      need a working copy stay off:
      <ul class="ps-4 my-1"><li v-for="item in limitations" :key="item">{{ item }}</li></ul>
      Everything else runs, including requirements, tech plans, repository scans, feature mapping and design
      system extraction.
    </AppCallout>

    <AiHostFields
      v-if="ai.caps.value && (ai.caps.value.requires_base_url || ai.caps.value.dynamic_models || ai.caps.value.supports_thinking)"
      v-model:base-url="ai.baseUrl.value"
      v-model:model="ai.model.value"
      v-model:thinking="ai.thinkingChoice.value"
      :caps="ai.caps.value"
      :deployment-mode="ai.deploymentMode.value"
    />

    <ChoiceTiles v-model="ai.authMode.value" :options="ai.tiles.value" label="Sign-in" />

    <div v-if="ai.requiresSecret.value">
      <PasswordField
        v-model="ai.credential.value"
        :label="ai.mode.value?.label ?? 'Credential'"
        :placeholder="ai.hasStoredCredential.value ? 'Saved. Leave blank to keep it.' : credentialPlaceholder(ai.provider.value, ai.authMode.value)"
        persistent-placeholder
        variant="outlined"
        density="compact"
        autocomplete="off"
        hide-details
      />
      <p v-if="ai.caps.value?.docs_url" class="ai-panel__hint">
        Where to get one: <a :href="ai.caps.value.docs_url" target="_blank" rel="noopener">{{ ai.caps.value.docs_url }}</a>
      </p>
    </div>

    <div class="ai-panel__actions">
      <v-btn color="primary" variant="flat" :loading="ai.saving.value" :disabled="!ai.canSave.value" @click="ai.save()">Save</v-btn>
      <v-btn variant="outlined" prepend-icon="mdi-connection" :loading="ai.test.value === 'checking'" @click="ai.runTest()">
        {{ ai.test.value === 'idle' ? 'Test connection' : 'Test again' }}
      </v-btn>
    </div>

    <AppCallout v-if="ai.test.value === 'failed'" variant="error">
      {{ ai.testError.value }}
      <div v-if="ai.showInstallHint.value && ai.caps.value?.install_hint" class="mt-1"><code>{{ ai.caps.value.install_hint }}</code></div>
    </AppCallout>
    <p v-if="ai.test.value === 'passed' && ai.testVersion.value" class="ai-panel__hint">{{ ai.testVersion.value }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import PasswordField from '@/components/common/PasswordField.vue'
import AiHostFields from '@/components/settings/ai/AiHostFields.vue'
import ChoiceTiles from '@/components/settings/ai/ChoiceTiles.vue'
import { useAiProviderSettings } from '@/composables/useAiProviderSettings'
import { providerLimitations, providerTitle } from '@/constants/aiProviders'
import { credentialPlaceholder, providerSummary, providerTiles } from '@/utils/aiProviderOptions'
import type { ProviderTest } from '@/utils/integrations'

const emit = defineEmits<{ test: [ProviderTest]; summary: [string] }>()

const ai = useAiProviderSettings()
const limitations = computed(() => providerLimitations(ai.caps.value))

watch(ai.test, t => emit('test', t), { immediate: true })
// The card describes what is saved, not the selection being edited.
watch([ai.savedCaps, ai.savedMode], () => emit('summary', providerSummary(ai.savedCaps.value, ai.savedMode.value)), {
  immediate: true,
})
const dirty = defineModel<boolean>('dirty', { default: false })
watch(ai.dirty, d => { dirty.value = d }, { immediate: true })

onMounted(() => {
  void ai.load()
})
</script>

<style scoped>
.ai-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.ai-panel__mode,
.ai-panel__hint {
  margin: 0;
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
  overflow-wrap: anywhere;
}
.ai-panel__hint {
  margin-top: 6px;
}
.ai-panel__hint a {
  color: var(--color-accent-text);
}
.ai-panel__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
