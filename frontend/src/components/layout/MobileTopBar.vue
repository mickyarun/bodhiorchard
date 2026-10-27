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

<!-- Phone-width top bar: menu button for the sidebar, the logo, and
     notifications. Desktop keeps these in the sidebar itself. -->
<template>
  <v-app-bar color="surface" flat density="comfortable" class="mobile-top-bar">
    <v-btn
      icon="mdi-menu"
      variant="text"
      :aria-expanded="drawer"
      aria-label="Open navigation"
      @click="drawer = !drawer"
    />
    <BrandLogo :size="24" />
    <v-spacer />
    <NotificationBell v-if="auth.user?.id" :user-id="auth.user.id" class="mr-2" />
  </v-app-bar>
</template>

<script setup lang="ts">
import BrandLogo from '@/components/common/BrandLogo.vue'
import NotificationBell from '@/components/common/NotificationBell.vue'
import { useAuthStore } from '@/stores/auth'

const drawer = defineModel<boolean>('drawer', { required: true })
const auth = useAuthStore()
</script>

<style scoped>
.mobile-top-bar {
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}
</style>
