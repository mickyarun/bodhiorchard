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
  <div class="d-flex flex-column align-center text-center">
    <v-icon
      icon="mdi-hand-wave-outline"
      size="48"
      color="primary"
      class="mb-4"
    />
    <h1 class="text-h4 font-weight-bold mb-2">
      Welcome to Bodhiorchard
    </h1>
    <p class="text-body-1 text-medium-emphasis mb-8" style="max-width: 520px;">
      The AI-native development platform — where intelligent agents and humans
      co-create software from idea to production
    </p>

    <v-row class="mb-8" justify="center">
      <v-col v-for="feature in features" :key="feature.title" cols="12" sm="4">
        <v-card
          class="pa-6 text-center card-border-dark h-100"
          color="surface"
        >
          <v-icon
            :icon="feature.icon"
            size="48"
            :color="feature.color"
            class="mb-4"
          />
          <div class="text-h6 font-weight-medium mb-2">
            {{ feature.title }}
          </div>
          <div class="text-body-2 text-medium-emphasis">
            {{ feature.description }}
          </div>
        </v-card>
      </v-col>
    </v-row>

    <v-btn
      color="primary"
      size="large"
      append-icon="mdi-arrow-right"
      @click="emit('getStarted')"
    >
      Get Started
    </v-btn>
  </div>
</template>

<script setup lang="ts">
const emit = defineEmits<{
  getStarted: []
}>()

const features = [
  {
    icon: 'mdi-account-group-outline',
    color: 'primary',
    title: 'Human + AI Loop',
    description: 'AI agents handle the heavy lifting while humans stay in control of every decision',
  },
  {
    icon: 'mdi-infinity',
    color: 'secondary',
    title: 'Idea to Production',
    description: 'From a chat message to deployed code — AI agents orchestrate every phase of the journey',
  },
  {
    icon: 'mdi-source-branch',
    color: 'success',
    title: 'Code-Native',
    description: 'Deep codebase understanding via Claude Code running on your own infrastructure',
  },
]
</script>
