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
  <v-row justify="center">
    <v-col cols="12" sm="6">
      <v-card class="pa-5 card-border-dark h-100" color="surface">
        <div class="d-flex align-center mb-3">
          <v-icon icon="mdi-robot-outline" color="primary" class="mr-2" />
          <div class="text-subtitle-1 font-weight-medium">AI Handles</div>
        </div>
        <div class="d-flex flex-column ga-2">
          <div v-for="item in aiHandles" :key="item" class="text-body-2 text-medium-emphasis">
            <v-icon icon="mdi-check" size="14" color="primary" class="mr-1" />
            {{ item }}
          </div>
        </div>
      </v-card>
    </v-col>
    <v-col cols="12" sm="6">
      <v-card class="pa-5 card-border-dark h-100" color="surface">
        <div class="d-flex align-center mb-3">
          <v-icon icon="mdi-account-outline" color="secondary" class="mr-2" />
          <div class="text-subtitle-1 font-weight-medium">Humans Handle</div>
        </div>
        <div class="d-flex flex-column ga-2">
          <div v-for="item in humanHandles" :key="item" class="text-body-2 text-medium-emphasis">
            <v-icon icon="mdi-check" size="14" color="secondary" class="mr-1" />
            {{ item }}
          </div>
        </div>
      </v-card>
    </v-col>
  </v-row>
</template>

<script setup lang="ts">
import { aiHandles, humanHandles } from '@/data/methodology'
</script>
