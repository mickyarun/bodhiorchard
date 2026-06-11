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
  <v-row>
    <v-col cols="12" md="6">
      <v-card class="pa-5 card-border-dark h-100" color="surface">
        <div class="d-flex align-center mb-3">
          <v-icon icon="mdi-database-sync-outline" color="primary" class="mr-2" />
          <div class="text-subtitle-1 font-weight-medium">Knowledge That Grows</div>
        </div>
        <p class="text-body-2 text-medium-emphasis mb-4">
          A 4-layer knowledge architecture that replaces stale wikis with living, auto-synced knowledge.
        </p>
        <div class="d-flex flex-column ga-2 mb-4">
          <div v-for="layer in knowledgeLayers" :key="layer.name" class="methodology-knowledge-layer">
            <div class="layer-number">{{ layer.num }}</div>
            <div>
              <div class="text-body-2 font-weight-medium">{{ layer.name }}</div>
              <div class="text-caption text-medium-emphasis">{{ layer.detail }}</div>
            </div>
          </div>
        </div>
        <div class="text-overline text-medium-emphasis mb-2">Why This Beats Confluence</div>
        <div class="d-flex flex-column ga-1">
          <div v-for="adv in knowledgeAdvantages" :key="adv" class="text-caption text-medium-emphasis">
            <v-icon icon="mdi-check-circle-outline" size="12" color="success" class="mr-1" />
            {{ adv }}
          </div>
        </div>
      </v-card>
    </v-col>
    <v-col cols="12" md="6">
      <v-card class="pa-5 card-border-dark h-100" color="surface">
        <div class="d-flex align-center mb-3">
          <v-icon icon="mdi-account-cog-outline" color="secondary" class="mr-2" />
          <div class="text-subtitle-1 font-weight-medium">Dev Skill Maintenance</div>
        </div>
        <p class="text-body-2 text-medium-emphasis mb-4">
          The Skill Agent rebuilds developer profiles daily — no manual updates, no stale resumes.
        </p>
        <div class="d-flex flex-column ga-3">
          <div v-for="item in skillItems" :key="item.label" class="d-flex align-start ga-2">
            <v-icon :icon="item.icon" size="18" color="secondary" class="mt-1 flex-shrink-0" />
            <div>
              <div class="text-body-2 font-weight-medium">{{ item.label }}</div>
              <div class="text-caption text-medium-emphasis">{{ item.detail }}</div>
            </div>
          </div>
        </div>
      </v-card>
    </v-col>
  </v-row>
</template>

<script setup lang="ts">
import { knowledgeLayers, knowledgeAdvantages, skillItems } from '@/data/methodology'
</script>

<style scoped>
.methodology-knowledge-layer {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.02);
  border-left: 3px solid rgb(var(--v-theme-primary));
  transition: background 0.2s ease;
}
.methodology-knowledge-layer:hover {
  background: rgba(255, 255, 255, 0.04);
}
.methodology-knowledge-layer .layer-number {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: rgba(var(--v-theme-primary), 0.2);
  color: rgb(var(--v-theme-primary));
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 0.7rem;
}
</style>
