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

<!-- The methodology / marketing content now lives on the public website
     (bodhiorchard.ai). This route exists only to redirect anyone who lands on
     the old in-app /methodology URL out to the live site. -->
<template>
  <v-app theme="bodhiorchardDark">
    <v-main class="d-flex flex-column align-center justify-center" style="min-height: 100vh;">
      <v-progress-circular indeterminate color="primary" size="40" class="mb-4" />
      <div class="text-body-2 text-medium-emphasis">Taking you to bodhiorchard.ai…</div>
    </v-main>
  </v-app>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'

const TARGET = 'https://bodhiorchard.ai/methodology'

onMounted(() => {
  // replace() so the back button doesn't bounce the user straight back here.
  window.location.replace(TARGET)
})
</script>
