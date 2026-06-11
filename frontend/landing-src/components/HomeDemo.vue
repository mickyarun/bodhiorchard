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

<!-- Featured tour video, lazy-loaded via a facade: the thumbnail ships in the
     HTML and the YouTube iframe is only mounted on click, keeping the Home
     page light. The full walkthrough grid lives on /platform. -->
<template>
  <section class="home-demo">
    <div class="text-center mb-5">
      <div class="text-h6 font-weight-medium">See the living orchard</div>
      <p class="text-caption text-medium-emphasis mx-auto" style="max-width: 520px;">
        A two-minute look at the Living Tree — your organization as a tended orchard.
      </p>
    </div>

    <v-card variant="outlined" class="home-demo__frame">
      <button v-if="!playing" type="button" class="home-demo__facade" aria-label="Play the tour" @click="playing = true">
        <img :src="`https://img.youtube.com/vi/${VIDEO_ID}/maxresdefault.jpg`" alt="" loading="lazy" />
        <v-icon icon="mdi-play-circle" size="76" class="home-demo__play" />
      </button>
      <iframe
        v-else
        :src="`https://www.youtube-nocookie.com/embed/${VIDEO_ID}?autoplay=1`"
        title="Bodhiorchard — Inside the virtual world"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
        allowfullscreen
      ></iframe>
    </v-card>

    <div class="text-center mt-5">
      <v-btn variant="text" to="/platform" append-icon="mdi-arrow-right">Explore the platform</v-btn>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const VIDEO_ID = 'OxoqBI7BNxU'
const playing = ref(false)
</script>

<style scoped>
.home-demo__frame {
  position: relative;
  aspect-ratio: 16 / 9;
  width: 100%;
  overflow: hidden;
  background: #0d1b0f;
}
.home-demo__facade {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  padding: 0;
  border: 0;
  cursor: pointer;
  background: #0d1b0f;
}
.home-demo__facade img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0.85;
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.home-demo__facade:hover img {
  opacity: 1;
  transform: scale(1.02);
}
.home-demo__play {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: rgba(255, 255, 255, 0.95);
  text-shadow: 0 0 14px rgba(0, 0, 0, 0.6);
  pointer-events: none;
}
.home-demo__frame iframe {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  border: 0;
}
</style>
