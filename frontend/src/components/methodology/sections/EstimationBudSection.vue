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
          <v-icon icon="mdi-chart-timeline-variant-shimmer" color="primary" class="mr-2" />
          <div class="text-subtitle-1 font-weight-medium">AI-PERT + Monte Carlo Estimation</div>
        </div>
        <div class="text-body-2 text-medium-emphasis mb-3">
          <span class="text-decoration-line-through text-error mr-1">Story points</span>
          <span class="text-decoration-line-through text-error mr-1">Planning poker</span>
          — replaced by probabilistic, per-phase delivery predictions that improve automatically.
        </div>
        <p class="text-body-2 text-medium-emphasis mb-3">
          AI generates optimistic, likely, and pessimistic estimates (PERT) for each phase.
          10,000 Monte Carlo simulations produce P50/P70/P85 confidence dates.
          Developer skill profiles, backlog depth, and workload are factored in.
        </p>
        <v-card variant="outlined" class="pa-3 mb-3" color="surface-variant">
          <div class="text-caption text-medium-emphasis mb-1">Example Prediction</div>
          <div class="text-body-2">
            <strong>Feature:</strong> Notification Redesign (Complexity: 3/5)
          </div>
          <div class="text-body-2 text-medium-emphasis">
            Developer: Alice (backend: 0.92, frontend: 0.35)
          </div>
          <div class="text-body-2 text-medium-emphasis">
            Go-live: 70% by Apr 25 | 85% by May 2
          </div>
        </v-card>
        <div class="d-flex flex-wrap ga-2">
          <v-chip color="primary" variant="tonal" size="small">PERT Analysis</v-chip>
          <v-chip color="secondary" variant="tonal" size="small">10K Simulations</v-chip>
          <v-chip color="success" variant="tonal" size="small">Skill-Aware</v-chip>
        </div>
      </v-card>
    </v-col>
    <v-col cols="12" md="6">
      <v-card class="pa-5 card-border-dark h-100" color="surface">
        <div class="d-flex align-center mb-3">
          <v-icon icon="mdi-file-document-check-outline" color="primary" class="mr-2" />
          <div class="text-subtitle-1 font-weight-medium">BUD (Business Understanding Document)</div>
        </div>
        <p class="text-body-2 text-medium-emphasis mb-3">
          Every feature lives in one <strong>BUD</strong> — a Business Understanding Document holding the spec, tech spec, test plan, acceptance criteria, and full history.
          Replaces scattered Jira tickets, Google Docs, and Notion pages.
        </p>
        <div class="d-flex flex-wrap ga-2 mb-4">
          <v-chip
            v-for="status in budStatuses"
            :key="status"
            variant="tonal"
            size="small"
            :color="status === 'deployed' ? 'success' : 'primary'"
          >
            {{ status }}
          </v-chip>
        </div>
        <div class="d-flex flex-column ga-2">
          <div v-for="item in budFeatures" :key="item" class="text-body-2 text-medium-emphasis">
            <v-icon icon="mdi-check" size="14" color="primary" class="mr-1" />
            {{ item }}
          </div>
        </div>
      </v-card>
    </v-col>
  </v-row>
</template>

<script setup lang="ts">
import { budStatuses, budFeatures } from '@/data/methodology'
</script>
