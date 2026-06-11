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
  <section class="vs-teaser card-border-dark">
    <div class="text-overline text-medium-emphasis mb-1">The old way vs Bodhiorchard</div>
    <h2 class="vs-teaser__title bo-display">Drop the ceremony. Keep what matters.</h2>

    <div class="vs-teaser__rows">
      <div v-for="row in VS_AGILE_TEASER" :key="row.phase" class="vs-teaser__row">
        <div class="vs-teaser__phase">{{ row.phase }}</div>
        <div class="vs-teaser__agile">
          <v-icon icon="mdi-close" size="14" class="mr-1" />{{ row.agile }}
        </div>
        <div class="vs-teaser__bodhi">
          <v-icon icon="mdi-check" size="14" color="primary" class="mr-1" />{{ row.bodhiorchard }}
        </div>
      </div>
    </div>

    <v-btn variant="text" to="/vs-agile" append-icon="mdi-arrow-right" class="mt-3">
      See the full comparison
    </v-btn>
  </section>
</template>

<script setup lang="ts">
import { VS_AGILE_TEASER } from '../content/site'
</script>

<style scoped>
.vs-teaser {
  border-radius: var(--radius-card, 10px);
  background: rgb(var(--v-theme-surface));
  padding: 32px 28px;
}
.vs-teaser__title {
  font-size: var(--text-lg, 1.5625rem);
  letter-spacing: var(--tracking-display, -0.02em);
  margin: 0 0 20px;
}
.vs-teaser__rows {
  display: flex;
  flex-direction: column;
}
.vs-teaser__row {
  display: grid;
  grid-template-columns: 130px 1fr 1fr;
  gap: 12px;
  align-items: center;
  padding: 14px 0;
  border-top: 1px solid rgb(var(--v-theme-rule));
  font-size: var(--text-sm, 0.9rem);
}
.vs-teaser__phase {
  font-weight: 600;
}
.vs-teaser__agile {
  color: rgb(var(--v-theme-on-surface-variant));
}
.vs-teaser__bodhi {
  color: rgb(var(--v-theme-on-surface));
}
@media (max-width: 640px) {
  .vs-teaser__row {
    grid-template-columns: 1fr;
    gap: 4px;
  }
}
</style>
