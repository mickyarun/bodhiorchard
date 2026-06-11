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
    <div class="text-overline text-medium-emphasis mb-4">Bodhiorchard vs Agile</div>
    <div style="overflow-x: auto;">
      <table class="methodology-comparison">
        <thead>
          <tr>
            <th>Phase</th>
            <th>Agile / Scrum</th>
            <th>Bodhiorchard</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in comparisonRows" :key="row.phase">
            <td>{{ row.phase }}</td>
            <td>{{ row.agile }}</td>
            <td>{{ row.bodhiorchard }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { comparisonRows } from '@/data/methodology'
</script>

<style scoped>
.methodology-comparison {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  border-radius: 8px;
  overflow: hidden;
  font-size: 0.875rem;
}
.methodology-comparison th {
  background: rgba(var(--v-theme-primary), 0.15);
  padding: 12px 16px;
  text-align: left;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.9);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
.methodology-comparison td {
  padding: 10px 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.7);
  vertical-align: top;
}
.methodology-comparison tr:nth-child(even) td {
  background: rgba(255, 255, 255, 0.02);
}
.methodology-comparison tr:hover td {
  background: rgba(255, 255, 255, 0.04);
}
.methodology-comparison td:first-child {
  font-weight: 500;
  color: rgba(255, 255, 255, 0.85);
  white-space: nowrap;
}
.methodology-comparison td:nth-child(2) {
  color: rgba(255, 255, 255, 0.45);
}
.methodology-comparison td:nth-child(3) {
  color: rgb(var(--v-theme-primary));
}
</style>
