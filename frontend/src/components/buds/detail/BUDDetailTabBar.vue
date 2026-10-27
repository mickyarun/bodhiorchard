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

<!-- The BUD section tabs, underlined, with the section toolbar (the
     default slot) at the end of the row. Sticks to the top while a long
     section scrolls. Tab values must match the v-tabs-window-item values
     on the page. -->
<template>
  <div class="detail-tabs">
    <v-tabs v-model="tab" color="primary" density="comfortable" show-arrows class="detail-tabs__tabs" aria-label="BUD sections">
      <v-tab v-for="t in tabs" :key="t.value" :value="t.value" class="detail-tabs__tab">{{ t.label }}</v-tab>
    </v-tabs>
    <div class="detail-tabs__tools"><slot /></div>
  </div>
</template>

<script setup lang="ts">
import type { DetailTab } from '@/utils/budDetail'

defineProps<{ tabs: DetailTab[] }>()
const tab = defineModel<string>({ required: true })
</script>

<style scoped>
.detail-tabs {
  position: sticky;
  top: 0;
  z-index: 5;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 4px 12px;
  background: rgb(var(--v-theme-background));
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}
.detail-tabs__tabs {
  min-width: 0;
  flex: 1 1 auto;
}
.detail-tabs__tab {
  font-size: 14px;
  font-weight: 500;
  min-width: 0;
  padding: 0 12px;
}
.detail-tabs__tools:empty {
  display: none;
}
</style>
