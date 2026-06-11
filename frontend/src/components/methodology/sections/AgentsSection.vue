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
      <v-icon icon="mdi-robot-happy-outline" size="32" color="primary" class="mb-2" />
      <div class="text-h6 font-weight-medium">Meet the Agents</div>
      <p class="text-caption text-medium-emphasis" style="max-width: 480px;">
        Twelve specialized agents orchestrate every phase — triggered automatically, connected to each other.
      </p>
    </div>
    <v-row dense>
      <v-col v-for="agent in agents" :key="agent.name" cols="12" sm="6" lg="3">
        <AgentCard :agent="agent" />
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import AgentCard from '@/components/setup/AgentCard.vue'
import { agents } from '@/data/agents'
</script>
