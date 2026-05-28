<!--
 * Copyright 2025-2026 Arun Rajkumar
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 -->

<template>
  <v-app>
    <v-app-bar flat color="surface" density="compact" class="landing-appbar">
      <div class="d-flex align-center justify-space-between w-100 px-4">
        <a href="https://bodhiorchard.ai/" class="landing-brand d-flex align-center text-decoration-none">
          <img src="/landing/bodhiorchard-logo-sm.png" width="28" height="28" alt="Bodhiorchard" />
          <span class="ml-2 text-subtitle-1 font-weight-bold">Bodhiorchard</span>
        </a>
        <v-btn
          color="primary"
          variant="flat"
          href="https://github.com/mickyarun/bodhiorchard"
          target="_blank"
          rel="noopener"
          prepend-icon="mdi-github"
        >
          GitHub
        </v-btn>
      </div>
    </v-app-bar>

    <v-main>
      <div class="pa-6" style="max-width: 1100px; margin: 0 auto;">
        <MethodologyStep @start-building="openGithub" />
      </div>
    </v-main>
  </v-app>
</template>

<script setup lang="ts">
import MethodologyStep from '@/views/setup/steps/MethodologyStep.vue'

function openGithub(): void {
  window.open('https://github.com/mickyarun/bodhiorchard', '_blank', 'noopener')
}
</script>

<style scoped>
.landing-appbar {
  border-bottom: 1px solid rgba(255, 255, 255, 0.06) !important;
}
.landing-brand,
.landing-brand:link,
.landing-brand:visited,
.landing-brand:hover,
.landing-brand:active {
  color: rgb(var(--v-theme-on-surface)) !important;
}
.landing-brand:hover {
  opacity: 0.85;
}
</style>
