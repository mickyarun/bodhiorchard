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
    <v-card variant="outlined">
      <div class="methodology-video-frame">
        <iframe
          :key="activeVideo.youTubeId"
          :src="`https://www.youtube-nocookie.com/embed/${activeVideo.youTubeId}`"
          :title="`Bodhiorchard — ${activeVideo.title}`"
          allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
          allowfullscreen
          loading="lazy"
        ></iframe>
      </div>
      <p class="text-caption text-center text-medium-emphasis py-3 mb-0 px-4">
        {{ activeVideo.caption }}
      </p>
    </v-card>

    <div class="text-overline text-medium-emphasis text-center mt-5 mb-2">
      More walkthroughs
    </div>
    <v-row dense justify="center">
      <v-col v-for="v in secondaryVideos" :key="v.value" cols="6" sm="4" md="2">
        <v-card
          variant="outlined"
          class="methodology-video-thumb"
          @click="videoTab = v.value"
        >
          <div class="methodology-video-thumb-img-wrap">
            <img
              :src="`https://img.youtube.com/vi/${v.youTubeId}/mqdefault.jpg`"
              :alt="v.title"
              loading="lazy"
              class="methodology-video-thumb-img"
            />
            <v-icon
              class="methodology-video-thumb-play"
              icon="mdi-play-circle"
              size="36"
            />
          </div>
          <div class="text-caption text-center text-medium-emphasis px-2 py-2">
            {{ v.title }}
          </div>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { demoVideos, HERO_VIDEO_VALUE, type DemoVideo } from '@/data/methodology'

const videoTab = ref<string>(HERO_VIDEO_VALUE)
const activeVideo = computed<DemoVideo>(
  () => demoVideos.find((v) => v.value === videoTab.value) ?? demoVideos[0],
)
const secondaryVideos = computed<DemoVideo[]>(
  () => demoVideos.filter((v) => v.value !== videoTab.value),
)
</script>

<style scoped>
.methodology-video-frame {
  position: relative;
  aspect-ratio: 16 / 9;
  width: 100%;
  background: #0d1b0f;
}
.methodology-video-frame iframe {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  border: 0;
  display: block;
}
.methodology-video-thumb {
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
  overflow: hidden;
  height: 100%;
}
.methodology-video-thumb:hover {
  transform: translateY(-2px);
  border-color: rgb(var(--v-theme-primary)) !important;
}
.methodology-video-thumb-img-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: #0d1b0f;
  overflow: hidden;
}
.methodology-video-thumb-img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.methodology-video-thumb-play {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: rgba(255, 255, 255, 0.92);
  text-shadow: 0 0 8px rgba(0, 0, 0, 0.55);
  pointer-events: none;
  opacity: 0.85;
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.methodology-video-thumb:hover .methodology-video-thumb-play {
  opacity: 1;
  transform: translate(-50%, -50%) scale(1.08);
}
</style>
