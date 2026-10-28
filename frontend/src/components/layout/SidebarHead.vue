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

<!-- Top of the sidebar: the mark, centred, on a collapsed rail; logo and
     wordmark when open or hovered. One fixed height in both, so nothing
     below it moves when a rail opens under the pointer. -->
<template>
  <div class="sidebar-head" :class="{ 'sidebar-head--collapsed': collapsed }">
    <BrandLogo :size="28" :show-text="!collapsed" />
  </div>
</template>

<script setup lang="ts">
import BrandLogo from '@/components/common/BrandLogo.vue'

defineProps<{ collapsed: boolean }>()
</script>

<style scoped>
.sidebar-head {
  display: flex;
  align-items: center;
  height: 64px;
  padding: 0 16px;
  border-bottom: 1px solid rgb(var(--v-theme-rule));
  margin-bottom: 4px;
}
.sidebar-head--collapsed {
  justify-content: center;
  padding: 0;
}
</style>
