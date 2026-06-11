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
    <div class="text-h6 font-weight-medium mb-4 text-center">The Flow</div>
    <LifecycleFlowchart class="mb-6" />

    <v-expansion-panels class="phase-expansion-panels" variant="accordion">
      <v-expansion-panel v-for="phase in phases" :key="phase.name">
        <v-expansion-panel-title>
          <div class="d-flex align-center ga-3">
            <v-icon :icon="phase.icon" size="20" color="primary" />
            <span class="font-weight-medium">{{ phase.name }}</span>
          </div>
        </v-expansion-panel-title>
        <v-expansion-panel-text>
          <p class="text-body-2 text-medium-emphasis mb-3">{{ phase.description }}</p>
          <v-row dense>
            <v-col cols="12" sm="6">
              <div class="d-flex align-center mb-2">
                <v-icon icon="mdi-robot-outline" size="16" color="primary" class="mr-1" />
                <span class="text-caption font-weight-medium">AI Role</span>
              </div>
              <div class="text-body-2 text-medium-emphasis">{{ phase.ai }}</div>
            </v-col>
            <v-col cols="12" sm="6">
              <div class="d-flex align-center mb-2">
                <v-icon icon="mdi-account-outline" size="16" color="secondary" class="mr-1" />
                <span class="text-caption font-weight-medium">Human Role</span>
              </div>
              <div class="text-body-2 text-medium-emphasis">{{ phase.human }}</div>
            </v-col>
          </v-row>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>
  </div>
</template>

<script setup lang="ts">
import LifecycleFlowchart from '@/components/setup/LifecycleFlowchart.vue'
import { phases } from '@/data/methodology'
</script>

<style scoped>
/* :deep() reaches the Vuetify-rendered panel internals from this scoped style. */
.phase-expansion-panels :deep(.v-expansion-panel) {
  background: rgba(255, 255, 255, 0.02) !important;
  border: 1px solid rgba(255, 255, 255, 0.04);
  margin-bottom: 4px;
}
.phase-expansion-panels :deep(.v-expansion-panel)::before {
  box-shadow: none !important;
}
.phase-expansion-panels :deep(.v-expansion-panel-title) {
  font-size: 0.9rem;
  min-height: 48px;
}
.phase-expansion-panels :deep(.v-expansion-panel-text__wrapper) {
  padding: 8px 16px 16px;
}
</style>
