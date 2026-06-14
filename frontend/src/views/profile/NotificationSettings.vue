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

<!-- Self-service notification settings page. Reached from the user menu
     (My Profile → Notification Settings); reuses NotificationPreferencesCard
     so the profile and this page can never drift. -->
<template>
  <v-container class="py-6" style="max-width: 760px;">
    <div class="d-flex align-center ga-2 mb-5">
      <v-btn
        icon="mdi-arrow-left"
        variant="text"
        size="small"
        density="comfortable"
        :to="{ name: 'profile' }"
        aria-label="Back to profile"
      />
      <v-icon icon="mdi-bell-cog-outline" size="24" />
      <div>
        <div class="text-h6 font-weight-bold bo-display">Notification Settings</div>
        <div class="text-caption text-medium-emphasis">
          Control which Slack messages our bot sends you
        </div>
      </div>
    </div>

    <NotificationPreferencesCard />
  </v-container>
</template>

<script setup lang="ts">
import NotificationPreferencesCard from '@/components/profile/NotificationPreferencesCard.vue'
</script>
