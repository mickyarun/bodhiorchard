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

<!-- Phone-width top bar: menu button for the sidebar, the logo, and the
     account cluster (notifications and the account menu). -->
<template>
  <v-app-bar color="surface" flat :height="TOP_BAR_HEIGHT" class="mobile-top-bar">
    <v-btn
      icon="mdi-menu"
      variant="text"
      :aria-expanded="drawer"
      aria-label="Open navigation"
      @click="drawer = !drawer"
    />
    <BrandLogo :size="24" />
    <v-spacer />
    <AccountCluster class="mr-2" />
  </v-app-bar>
</template>

<script setup lang="ts">
import BrandLogo from '@/components/common/BrandLogo.vue'
import AccountCluster from '@/components/layout/AccountCluster.vue'
import { TOP_BAR_HEIGHT } from '@/constants/layout'

const drawer = defineModel<boolean>('drawer', { required: true })
</script>

<style scoped>
.mobile-top-bar {
  box-shadow: inset 0 -1px 0 rgb(var(--v-theme-rule));
}
</style>
