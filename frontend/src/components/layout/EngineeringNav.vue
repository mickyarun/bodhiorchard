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

<!-- Sidebar links for the engineering workspace. Rendered only for
     members holding ``workspace:engineering``. -->
<template>
  <v-list-item
    prepend-icon="mdi-view-dashboard-outline"
    title="Dashboard"
    to="/dashboard"
    rounded="lg"
  />
  <v-list-item
    prepend-icon="mdi-seed-outline"
    title="BUDs"
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
    prepend-icon="mdi-trophy-outline"
    title="Leaderboard"
    to="/leaderboard"
    rounded="lg"
  />
  <v-list-item
    prepend-icon="mdi-account-cog-outline"
    title="Skills"
    to="/skills"
    rounded="lg"
  />
  <v-list-item
    prepend-icon="mdi-book-open-page-variant-outline"
    title="Learnings"
    to="/learnings"
    rounded="lg"
  />
  <v-list-item
    v-if="canApprove"
    prepend-icon="mdi-clipboard-check-outline"
    title="Triage"
    to="/triage"
    rounded="lg"
  />
  <v-list-item
    v-if="canManageMembers"
    prepend-icon="mdi-account-group-outline"
    title="Members"
    to="/members"
    rounded="lg"
  />
</template>

<script setup lang="ts">
import { usePermissions } from '@/composables/usePermissions'

const { canApprove, canManageMembers } = usePermissions()
</script>
