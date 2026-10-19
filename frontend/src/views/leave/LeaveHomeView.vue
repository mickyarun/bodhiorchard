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

<!-- Leave home. The landing page for every member outside the
     engineering workspace (sales, HR); balances, requests and the team
     calendar build on this page. -->
<template>
  <div class="pa-6 leave-home">
    <div class="mb-6">
      <h1 class="text-h5 font-weight-bold bo-display">Leave</h1>
      <p class="text-body-2 text-medium-emphasis">
        Request leave and work from home, and see who's out.
      </p>
    </div>
    <AppCallout variant="info" eyebrow="Not set up yet" icon="mdi-beach">
      Leave and work-from-home requests aren't switched on for your organization yet. Your
      notification settings are available from the menu in the bottom left.
    </AppCallout>
  </div>
</template>

<script setup lang="ts">
import AppCallout from '@/components/common/AppCallout.vue'
</script>

<style scoped>
.leave-home {
  max-width: 1120px;
}
</style>
