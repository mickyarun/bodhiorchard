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
  <div>
    <div class="d-flex flex-column align-center text-center mb-5">
      <v-icon icon="mdi-trophy-outline" size="32" color="secondary" class="mb-2" />
      <div class="text-h6 font-weight-medium">The gamification layer</div>
      <p class="text-caption text-medium-emphasis" style="max-width: 560px;">
        The Skill Agent rebuilds developer profiles nightly. Skills compound, badges unlock, and the leaderboard reflects what people shipped — not how many tickets they touched.
      </p>
    </div>
    <v-row dense>
      <v-col v-for="shot in gamificationShots" :key="shot.src" cols="12" sm="6" lg="3">
        <v-card class="methodology-shot-card" variant="outlined" @click="openLightbox(shot)">
          <img :src="shot.src" :alt="shot.alt" loading="lazy" class="methodology-shot-img" />
        </v-card>
      </v-col>
    </v-row>

    <ScreenshotLightbox
      v-model="lightboxOpen"
      :src="lightboxShot.src"
      :alt="lightboxShot.alt"
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import ScreenshotLightbox from '@/components/methodology/ScreenshotLightbox.vue'
import { gamificationShots, type Shot } from '@/data/methodology'

const lightboxOpen = ref(false)
const lightboxShot = ref<Shot>({ src: '', alt: '' })
function openLightbox(shot: Shot): void {
  lightboxShot.value = shot
  lightboxOpen.value = true
}
</script>

<style scoped>
.methodology-shot-card {
  cursor: zoom-in;
  transition: transform 0.18s ease, border-color 0.18s ease;
  overflow: hidden;
}
.methodology-shot-card:hover {
  transform: translateY(-2px);
  border-color: rgb(var(--v-theme-primary)) !important;
}
.methodology-shot-img {
  display: block;
  width: 100%;
  aspect-ratio: 4 / 3;
  object-fit: cover;
}
</style>
