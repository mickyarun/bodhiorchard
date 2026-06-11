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
  <header class="methodology-hero">
    <img
      :src="logoSrc"
      width="56"
      height="56"
      alt="Bodhiorchard"
      class="methodology-hero__mark"
    />
    <div class="methodology-hero__eyebrow">An AI-native way to build software</div>
    <h1 class="methodology-hero__title bo-display">
      The Bodhiorchard Methodology
    </h1>
    <p class="methodology-hero__lede">
      From conversation to production — every phase powered by intelligent
      agents working alongside humans, in a living garden you can watch grow.
    </p>
    <div class="methodology-hero__actions">
      <v-btn
        color="primary"
        variant="flat"
        size="large"
        append-icon="mdi-arrow-right"
        @click="emit('startBuilding')"
      >
        Start Building
      </v-btn>
      <v-btn
        v-if="showTour"
        variant="text"
        size="large"
        prepend-icon="mdi-play-circle-outline"
        @click="emit('watchTour')"
      >
        Watch the tour
      </v-btn>
    </div>
  </header>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    // Both the in-app and landing public dirs ship /assets/bodhiorchard-logo-sm.png.
    logoSrc?: string
    showTour?: boolean
  }>(),
  {
    logoSrc: '/assets/bodhiorchard-logo-sm.png',
    showTour: true,
  },
)

const emit = defineEmits<{
  startBuilding: []
  watchTour: []
}>()
</script>

<style scoped>
.methodology-hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 28px 0 56px;
}
.methodology-hero__mark {
  border-radius: 50%;
  margin-bottom: 20px;
}
.methodology-hero__eyebrow {
  font-size: var(--text-sm, 0.9rem);
  text-transform: uppercase;
  letter-spacing: var(--tracking-label, 0.08em);
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
  margin-bottom: 14px;
}
.methodology-hero__title {
  font-size: var(--text-display, clamp(2.25rem, 4vw + 1rem, 3.75rem));
  line-height: 1.05;
  letter-spacing: var(--tracking-display, -0.02em);
  max-width: 16ch;
  margin: 0 0 18px;
  overflow-wrap: anywhere;
}
.methodology-hero__lede {
  font-size: var(--text-md, 1.25rem);
  line-height: 1.55;
  color: rgb(var(--v-theme-on-surface-variant));
  max-width: 58ch;
  margin: 0 0 28px;
}
.methodology-hero__actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: center;
}
</style>
