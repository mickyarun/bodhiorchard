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
  <section>
    <v-row dense>
      <v-col v-for="(h, i) in HOME_HIGHLIGHTS" :key="h.title" cols="12" sm="6">
        <ScrollReveal :delay="i * 70">
          <SpotlightCard class="h-100">
            <router-link :to="h.to" class="highlight__link">
              <v-icon :icon="h.icon" size="26" color="primary" class="mb-3" />
              <h3 class="highlight__title">{{ h.title }}</h3>
              <p class="highlight__body">{{ h.body }}</p>
            </router-link>
          </SpotlightCard>
        </ScrollReveal>
      </v-col>
    </v-row>
  </section>
</template>

<script setup lang="ts">
import ScrollReveal from '@/components/landing/effects/ScrollReveal.vue'
import SpotlightCard from '@/components/landing/effects/SpotlightCard.vue'
import { HOME_HIGHLIGHTS } from '../content/site'
</script>

<style scoped>
.highlight__link {
  display: block;
  padding: 24px;
  text-decoration: none;
  color: inherit;
}
.highlight__title {
  font-size: var(--text-md, 1.25rem);
  font-weight: 600;
  margin: 0 0 8px;
  color: rgb(var(--v-theme-on-surface));
}
.highlight__body {
  font-size: var(--text-sm, 0.9rem);
  line-height: 1.55;
  color: rgb(var(--v-theme-on-surface-variant));
  margin: 0;
}
</style>
