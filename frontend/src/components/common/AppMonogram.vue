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

<!-- A person's initials on the accent wash. Decorative: the name is always
     written beside it, so it stays out of the accessibility tree.
     ``square`` gives the rounded-square shape used for message authors. -->
<template>
  <span
    class="app-monogram"
    :class="{ 'app-monogram--square': square }"
    :style="{ '--size': `${size}px` }"
    aria-hidden="true"
  >{{ initialsOf(name || '?') }}</span>
</template>

<script setup lang="ts">
import { initialsOf } from '@/utils/avatar'

withDefaults(defineProps<{ name: string | null | undefined; size?: number; square?: boolean }>(), {
  size: 32,
  square: false,
})
</script>

<style scoped>
.app-monogram {
  width: var(--size);
  height: var(--size);
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  font-size: calc(var(--size) * 0.34);
  font-weight: 600;
  color: var(--color-accent-text);
  background: var(--color-accent-soft);
}
.app-monogram--square {
  border-radius: 8px;
}
</style>
