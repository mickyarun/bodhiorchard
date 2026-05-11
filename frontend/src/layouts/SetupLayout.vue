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
  <div class="setup-gradient d-flex flex-column">
    <v-container class="d-flex flex-column align-center flex-grow-1 py-8">
      <div class="mb-8">
        <BodhiorchardLogo />
      </div>
      <v-sheet
        class="flex-grow-1 w-100"
        color="transparent"
        :max-width="720"
      >
        <router-view />
      </v-sheet>
    </v-container>
  </div>
</template>

<script setup lang="ts">
import BodhiorchardLogo from '@/components/common/BodhiorchardLogo.vue'
</script>
