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
  <LandingContainer>
    <div class="not-found">
      <div class="not-found__code bo-display">404</div>
      <h1 class="not-found__title bo-display">This branch never grew.</h1>
      <p class="not-found__lede">The page you’re looking for isn’t here — but the orchard is.</p>
      <v-btn color="primary" variant="flat" to="/" prepend-icon="mdi-home-outline">Back to home</v-btn>
    </div>
  </LandingContainer>
</template>

<script setup lang="ts">
import LandingContainer from '../components/LandingContainer.vue'
import { useSeo } from '../composables/useSeo'

useSeo({
  title: 'Page not found | Bodhiorchard',
  description: 'The page you’re looking for isn’t here.',
  path: '/404',
  noindex: true,
})
</script>

<style scoped>
.not-found {
  text-align: center;
  padding: 120px 20px;
  max-width: 36ch;
  margin: 0 auto;
}
.not-found__code {
  font-size: 5rem;
  line-height: 1;
  color: rgb(var(--v-theme-primary));
}
.not-found__title {
  font-size: var(--text-xl, 1.953rem);
  margin: 8px 0 12px;
}
.not-found__lede {
  color: rgb(var(--v-theme-on-surface-variant));
  margin-bottom: 24px;
}
</style>
