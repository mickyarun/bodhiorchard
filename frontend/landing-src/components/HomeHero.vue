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
  <section class="home-hero">
    <AuroraBackground />
    <div class="home-hero__inner">
      <div class="home-hero__eyebrow">The open-source alternative to sprint, scrum &amp; agile</div>
      <h1 class="home-hero__title bo-display">
        From conversation to production, with
        <GradientText>twelve AI agents</GradientText>.
      </h1>
      <p class="home-hero__lede">
        Bodhiorchard replaces story points, standups, and stale tickets with specialised
        agents that draft every spec, forecast every cycle time, and tend your codebase
        like an orchard — so humans can focus on what actually matters.
      </p>
      <div class="home-hero__actions">
        <v-btn
          color="primary"
          variant="flat"
          size="large"
          prepend-icon="mdi-github"
          :href="GITHUB_URL"
          target="_blank"
          rel="noopener"
        >
          Get started on GitHub
        </v-btn>
        <v-btn variant="outlined" size="large" to="/methodology" append-icon="mdi-arrow-right">
          See the methodology
        </v-btn>
      </div>

      <div class="home-hero__proof">
        <span v-for="p in SOCIAL_PROOF" :key="p.label" class="home-hero__proof-item">
          <v-icon :icon="p.icon" size="16" class="mr-1" />{{ p.label }}
        </span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import AuroraBackground from '@/components/landing/effects/AuroraBackground.vue'
import GradientText from '@/components/landing/effects/GradientText.vue'
import { GITHUB_URL, SOCIAL_PROOF } from '../content/site'
</script>

<style scoped>
.home-hero {
  position: relative;
  overflow: hidden;
  padding: 96px 20px 72px;
}
.home-hero__inner {
  position: relative;
  z-index: 1;
  max-width: 880px;
  margin: 0 auto;
  text-align: center;
}
.home-hero__eyebrow {
  font-size: var(--text-sm, 0.9rem);
  text-transform: uppercase;
  letter-spacing: var(--tracking-label, 0.08em);
  font-weight: 600;
  color: rgb(var(--v-theme-primary));
  margin-bottom: 18px;
}
.home-hero__title {
  font-size: clamp(2.5rem, 5vw + 1rem, 4.25rem);
  line-height: 1.04;
  letter-spacing: var(--tracking-display, -0.02em);
  margin: 0 0 22px;
  overflow-wrap: anywhere;
}
.home-hero__lede {
  font-size: var(--text-md, 1.25rem);
  line-height: 1.55;
  color: rgb(var(--v-theme-on-surface-variant));
  max-width: 60ch;
  margin: 0 auto 30px;
}
.home-hero__actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: center;
  margin-bottom: 34px;
}
.home-hero__proof {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 22px;
  justify-content: center;
}
.home-hero__proof-item {
  display: inline-flex;
  align-items: center;
  font-size: var(--text-sm, 0.9rem);
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
