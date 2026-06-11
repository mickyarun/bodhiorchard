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

<!-- Consistent page header (eyebrow + display title + optional lede). -->
<template>
  <header class="page-heading">
    <div v-if="eyebrow" class="page-heading__eyebrow">{{ eyebrow }}</div>
    <h1 class="page-heading__title bo-display">{{ title }}</h1>
    <p v-if="lede" class="page-heading__lede">{{ lede }}</p>
  </header>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  eyebrow?: string
  lede?: string
}>()
</script>

<style scoped>
.page-heading {
  text-align: center;
  max-width: 64ch;
  margin: 0 auto 40px;
}
.page-heading__eyebrow {
  font-size: var(--text-sm, 0.9rem);
  text-transform: uppercase;
  letter-spacing: var(--tracking-label, 0.08em);
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
  margin-bottom: 12px;
}
.page-heading__title {
  font-size: var(--text-2xl, 2.441rem);
  line-height: 1.08;
  letter-spacing: var(--tracking-display, -0.02em);
  margin: 0;
  overflow-wrap: anywhere;
}
.page-heading__lede {
  font-size: var(--text-md, 1.25rem);
  line-height: 1.55;
  color: rgb(var(--v-theme-on-surface-variant));
  margin: 16px auto 0;
}
</style>
