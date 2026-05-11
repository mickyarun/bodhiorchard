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
  <v-card class="agent-card card-border-dark h-100 d-flex flex-column" color="surface">
    <!-- Colored top accent -->
    <div class="agent-card__accent" :style="{ background: `rgb(var(--v-theme-${agent.color}))` }" />

    <div class="pa-4 d-flex flex-column flex-grow-1">
      <!-- Header: icon + name + trigger -->
      <div class="d-flex align-center mb-2">
        <v-avatar :color="agent.color" size="32" variant="tonal" class="mr-2">
          <v-icon :icon="agent.icon" size="18" />
        </v-avatar>
        <div class="flex-grow-1">
          <div class="text-subtitle-2 font-weight-bold">{{ agent.name }}</div>
        </div>
      </div>

      <v-chip
        :prepend-icon="agent.triggerIcon"
        size="x-small"
        variant="tonal"
        :color="agent.color"
        class="mb-3 align-self-start"
      >
        {{ agent.triggerType }}
      </v-chip>

      <!-- Short tagline -->
      <p class="text-caption text-medium-emphasis mb-3">{{ agent.tagline }}</p>

      <!-- Capabilities as compact chips -->
      <div class="d-flex flex-wrap ga-1 mb-3">
        <v-chip
          v-for="cap in agent.capabilities"
          :key="cap"
          size="x-small"
          variant="outlined"
          :color="agent.color"
          class="agent-cap-chip"
        >
          {{ cap }}
        </v-chip>
      </div>

      <!-- Connects to -->
      <div v-if="agent.interactsWith.length" class="mt-auto pt-2" style="border-top: 1px solid rgba(255,255,255,0.04);">
        <div class="d-flex flex-wrap align-center ga-1">
          <v-icon icon="mdi-link-variant" size="12" class="text-medium-emphasis" />
          <span
            v-for="(name, i) in agent.interactsWith"
            :key="name"
            class="text-caption text-medium-emphasis"
          >{{ name }}<span v-if="i < agent.interactsWith.length - 1">,</span></span>
        </div>
      </div>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import type { AgentInfo } from '@/data/agents'

defineProps<{
  agent: AgentInfo
}>()
</script>
