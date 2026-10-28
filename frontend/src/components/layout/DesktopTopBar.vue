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

<!-- Wide-screen top bar (960px and up; narrower screens use the phone
     bar): a slim strip above the page, beside the sidebar, holding only
     the account cluster at the top right. It sits on the page background
     with a hairline, so page headers below keep their own spacing and
     actions. It shares TOP_BAR_HEIGHT with the sidebar's logo row, and
     both draw their hairline inside that height, so the lines meet. -->
<template>
  <v-app-bar flat :height="TOP_BAR_HEIGHT" color="background" class="desktop-top-bar">
    <v-spacer />
    <AccountCluster class="desktop-top-bar__cluster" />
  </v-app-bar>
</template>

<script setup lang="ts">
import AccountCluster from '@/components/layout/AccountCluster.vue'
import { TOP_BAR_HEIGHT } from '@/constants/layout'
</script>

<style scoped>
.desktop-top-bar {
  box-shadow: inset 0 -1px 0 rgb(var(--v-theme-rule));
}
/* Pages pad their sides by 36px; the avatar sits 4px inside its button,
   so 32px puts it roughly in line with the page content's right edge
   (pages that scroll sit a scrollbar's width further in). */
.desktop-top-bar__cluster {
  margin-right: 32px;
}
</style>
