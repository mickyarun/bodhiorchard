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
  <v-card class="pa-6 card-border-dark" color="surface">
    <div class="text-overline text-medium-emphasis mb-4">Our Manifesto</div>
    <v-row dense>
      <v-col v-for="(principle, index) in principles" :key="index" cols="12" sm="6">
        <div
          class="methodology-principle"
          :class="index % 2 === 0 ? 'border-primary' : 'border-secondary'"
        >
          <v-icon
            :icon="principle.icon"
            size="16"
            :color="index % 2 === 0 ? 'primary' : 'secondary'"
            class="mr-2 flex-shrink-0"
          />
          <span class="text-body-2">
            <strong :class="index % 2 === 0 ? 'text-primary' : 'text-secondary'">{{ principle.value }}</strong>
            <span class="text-medium-emphasis"> over {{ principle.over }}</span>
          </span>
        </div>
      </v-col>
    </v-row>
  </v-card>
</template>

<script setup lang="ts">
import { principles } from '@/data/methodology'
</script>

<style scoped>
.methodology-principle {
  display: flex;
  align-items: center;
  padding: 10px 14px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.02);
  transition: background 0.2s ease;
}
.methodology-principle:hover {
  background: rgba(255, 255, 255, 0.05);
}
.methodology-principle.border-primary {
  border-left: 3px solid rgb(var(--v-theme-primary));
}
.methodology-principle.border-secondary {
  border-left: 3px solid rgb(var(--v-theme-secondary));
}
</style>
