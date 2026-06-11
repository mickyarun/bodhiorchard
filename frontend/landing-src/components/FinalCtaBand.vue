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

<!-- Reusable closing call-to-action band with an animated border beam. -->
<template>
  <section class="cta-band">
    <div class="cta-band__card card-border-dark">
      <BorderBeam />
      <h2 class="cta-band__title bo-display">{{ title }}</h2>
      <p v-if="subtitle" class="cta-band__sub">{{ subtitle }}</p>
      <v-btn
        color="primary"
        size="large"
        :href="GITHUB_URL"
        target="_blank"
        rel="noopener"
        prepend-icon="mdi-github"
        append-icon="mdi-arrow-right"
      >
        {{ ctaLabel }}
      </v-btn>
    </div>
  </section>
</template>

<script setup lang="ts">
import BorderBeam from '@/components/landing/effects/BorderBeam.vue'
import { GITHUB_URL } from '../content/site'

withDefaults(
  defineProps<{
    title: string
    subtitle?: string
    ctaLabel?: string
  }>(),
  {
    subtitle: '',
    ctaLabel: 'Get started on GitHub',
  },
)
</script>

<style scoped>
.cta-band {
  padding: 8px 0 16px;
}
.cta-band__card {
  position: relative;
  overflow: hidden;
  border-radius: var(--radius-card, 10px);
  background: rgb(var(--v-theme-surface));
  text-align: center;
  padding: 56px 24px;
}
.cta-band__title {
  font-size: var(--text-xl, 1.953rem);
  letter-spacing: var(--tracking-display, -0.02em);
  margin: 0 0 10px;
}
.cta-band__sub {
  color: rgb(var(--v-theme-on-surface-variant));
  max-width: 52ch;
  margin: 0 auto 24px;
}
</style>
