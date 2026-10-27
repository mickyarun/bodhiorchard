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

<!-- Sidebar links for the engineering workspace, in two groups: day-to-day
     work and the read-only insight views. Rendered only for members holding
     ``workspace:engineering``. -->
<template>
  <NavHeading label="Work" :rail="rail" />
  <v-list-item
    prepend-icon="mdi-view-dashboard-outline"
    title="Dashboard"
    to="/dashboard"
    rounded="lg"
  />
  <v-list-item
    prepend-icon="mdi-view-column-outline"
    title="Board"
    to="/buds"
    rounded="lg"
  />
  <v-list-item
    prepend-icon="mdi-lightbulb-outline"
    title="Features"
    to="/features"
    rounded="lg"
  />
  <v-list-item
    prepend-icon="mdi-bug-outline"
    title="Bugs"
    to="/bugs"
    rounded="lg"
  />
  <v-list-item
    v-if="canApprove"
    prepend-icon="mdi-inbox-outline"
    title="Triage"
    to="/triage"
    rounded="lg"
  />

  <NavHeading label="Insights" :rail="rail" />
  <v-list-item
    prepend-icon="mdi-trophy-outline"
    title="Leaderboard"
    to="/leaderboard"
    rounded="lg"
  />
  <v-list-item
    prepend-icon="mdi-target"
    title="Skills"
    to="/skills"
    rounded="lg"
  />
  <v-list-item
    prepend-icon="mdi-chart-bar"
    title="Learnings"
    to="/learnings"
    rounded="lg"
  />
</template>

<script setup lang="ts">
import NavHeading from '@/components/layout/NavHeading.vue'
import { usePermissions } from '@/composables/usePermissions'

defineProps<{ rail: boolean }>()

const { canApprove } = usePermissions()
</script>
