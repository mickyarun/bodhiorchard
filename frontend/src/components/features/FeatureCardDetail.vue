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

<!-- The expanded part of a feature card: capabilities, backend
     dependencies with their API paths, and the code locations with a copy
     button. -->
<template>
  <div class="feature-detail">
    <section v-if="capabilities.length">
      <h4>Capabilities</h4>
      <ul class="feature-detail__caps">
        <li v-for="cap in capabilities" :key="cap">{{ cap }}</li>
      </ul>
    </section>

    <section v-if="feature.backendLinks.length">
      <h4>Backend dependencies</h4>
      <div v-for="link in feature.backendLinks" :key="link.repoId" class="feature-detail__dep">
        <span class="feature-detail__dep-name">{{ link.repoName }}</span>
        <code v-for="path in link.apiPaths" :key="path">{{ path }}</code>
      </div>
    </section>

    <section v-if="locations.size">
      <div class="feature-detail__head">
        <h4>Code locations</h4>
        <v-btn variant="text" size="small" :prepend-icon="copied ? 'mdi-check' : 'mdi-content-copy'" @click="copy">
          {{ copied ? 'Copied' : 'Copy' }}
        </v-btn>
      </div>
      <pre class="feature-detail__locs"><code>{{ locationsText }}</code></pre>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Feature } from '@/types'
import { copyText } from '@/utils/clipboard'
import { codeLocations, codeLocationsText, featureCapabilities } from '@/utils/featureCard'

const props = defineProps<{ feature: Feature }>()

const capabilities = computed(() => featureCapabilities(props.feature))
const locations = computed(() => codeLocations(props.feature))
const locationsText = computed(() => codeLocationsText(locations.value))
const copied = ref(false)

async function copy(): Promise<void> {
  if (!(await copyText(locationsText.value))) return
  copied.value = true
  setTimeout(() => (copied.value = false), 1500)
}
</script>

<style scoped>
.feature-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-top: 14px;
  border-top: 1px solid rgb(var(--v-theme-rule));
}
h4 {
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface-variant));
}
.feature-detail__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.feature-detail__head h4 {
  margin: 0;
}
.feature-detail__caps {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 20px;
}
.feature-detail__dep {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}
.feature-detail__dep-name {
  font-weight: 600;
  margin-right: 4px;
}
code {
  font-family: var(--font-mono);
  font-size: 12px;
}
.feature-detail__dep code {
  padding: 1px 6px;
  border-radius: 5px;
  background: rgb(var(--v-theme-surface-variant));
}
.feature-detail__locs {
  margin: 6px 0 0;
  padding: 10px 12px;
  max-height: 220px;
  overflow: auto;
  border-radius: 8px;
  background: rgb(var(--v-theme-background));
  border: 1px solid rgb(var(--v-theme-rule));
  line-height: 18px;
}
</style>
