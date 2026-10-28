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

<!-- Desktop and tablet top bar: a slim strip above the page, beside the
     sidebar, holding only the account cluster at the top right. It sits
     on the page background with a hairline, so page headers below keep
     their own spacing and actions. Its 56px height matches the sidebar's
     logo row (SidebarHead), so the two hairlines meet in one line. -->
<template>
  <v-app-bar flat :height="56" color="background" class="desktop-top-bar">
    <v-spacer />
    <AccountCluster class="desktop-top-bar__cluster" />
  </v-app-bar>
</template>

<script setup lang="ts">
import AccountCluster from '@/components/layout/AccountCluster.vue'
</script>

<style scoped>
.desktop-top-bar {
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}
/* Lines the cluster up with the page content's right edge. */
.desktop-top-bar__cluster {
  margin-right: 28px;
}
</style>
