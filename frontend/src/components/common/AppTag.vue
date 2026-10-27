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

<!-- A small status or severity tag: the theme colour as text on a wash of
     itself. ``color`` is a theme colour name (``error``, ``priority-p1``,
     ``stage-testing`` …); leave it out for a neutral tag. -->
<template>
  <span class="app-tag" :style="{ '--tag': `var(--v-theme-${color})` }">
    <span v-if="srPrefix" class="d-sr-only">{{ srPrefix }} </span><slot />
  </span>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ color?: string; srPrefix?: string }>(), {
  color: 'on-surface-variant',
  srPrefix: '',
})
</script>

<style scoped>
.app-tag {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  line-height: 18px;
  white-space: nowrap;
  color: rgb(var(--tag));
  background: rgba(var(--tag), 0.14);
}
</style>
