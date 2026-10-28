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

<!-- Top of the sidebar. Collapsed rail: the mark with the bell under it,
     both centred. Open (or hovered) sidebar: logo and wordmark, bell at
     the end. The bell shows in both, so its menu keeps its trigger when
     the pointer leaves a hovered rail to reach the dropdown. -->
<template>
  <div class="sidebar-head" :class="{ 'sidebar-head--collapsed': collapsed }">
    <BrandLogo :size="28" :show-text="!collapsed" />
    <NotificationBell v-if="auth.user?.id" :user-id="auth.user.id" />
  </div>
</template>

<script setup lang="ts">
import BrandLogo from '@/components/common/BrandLogo.vue'
import NotificationBell from '@/components/common/NotificationBell.vue'
import { useAuthStore } from '@/stores/auth'

defineProps<{ collapsed: boolean }>()
const auth = useAuthStore()
</script>

<style scoped>
.sidebar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 64px;
  padding: 12px 12px 8px 16px;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
  margin-bottom: 4px;
}
.sidebar-head--collapsed {
  flex-direction: column;
  justify-content: center;
  padding: 12px 0 8px;
}
</style>
