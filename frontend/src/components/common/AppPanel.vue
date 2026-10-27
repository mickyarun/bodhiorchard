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

<!-- A titled surface card: hairline border, no shadow, a heading row with
     an optional note and a trailing action (usually a text link).

       <AppPanel title="Flow" note="Where every open BUD is right now">
         <template #action><router-link to="/buds">Open board</router-link></template>
         …
       </AppPanel>

     ``flush`` drops the body padding so a list can run edge to edge with
     its own row dividers. -->
<template>
  <section class="app-panel" :class="{ 'app-panel--flush': flush }" :aria-labelledby="headingId">
    <header class="app-panel__head">
      <h2 :id="headingId" class="app-panel__title">{{ title }}</h2>
      <span v-if="note" class="app-panel__note">{{ note }}</span>
      <span class="app-panel__action"><slot name="action" /></span>
    </header>
    <div class="app-panel__body"><slot /></div>
  </section>
</template>

<script setup lang="ts">
import { useId } from 'vue'

defineProps<{
  title: string
  note?: string
  flush?: boolean
}>()

const headingId = useId()
</script>

<style scoped>
.app-panel {
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
  padding: 18px 20px;
  min-width: 0;
}
.app-panel--flush {
  padding: 0;
}
.app-panel__head {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 4px 12px;
  margin-bottom: 12px;
}
.app-panel--flush .app-panel__head {
  padding: 18px 20px 0;
}
.app-panel__title {
  margin: 0;
  font-size: var(--text-base);
  font-weight: 600;
  line-height: 1.4;
}
.app-panel__note {
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.app-panel__action {
  margin-left: auto;
  font-size: 13px;
  font-weight: 500;
}
.app-panel__action :deep(a) {
  color: var(--color-accent-text);
  text-decoration: none;
}
.app-panel__action :deep(a:hover) {
  text-decoration: underline;
}
</style>
