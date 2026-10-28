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

<!-- A person's initials on a tonal wash. Decorative by default: the name is
     usually written beside it, so it stays out of the accessibility tree.
     Pass ``label`` when it stands alone and must be announced.
     ``square`` gives the rounded-square shape used for message authors;
     ``tone="brand"`` uses the indigo brand wash instead of the accent blue. -->
<template>
  <span
    class="app-monogram"
    :class="{ 'app-monogram--square': square, 'app-monogram--brand': tone === 'brand' }"
    :style="{ '--size': `${size}px` }"
    :role="label ? 'img' : undefined"
    :aria-label="label"
    :aria-hidden="label ? undefined : 'true'"
  >{{ initialsOf(name || '?') }}</span>
</template>

<script setup lang="ts">
import { initialsOf } from '@/utils/avatar'

withDefaults(
  defineProps<{
    name: string | null | undefined
    size?: number
    square?: boolean
    tone?: 'accent' | 'brand'
    label?: string
  }>(),
  { size: 32, square: false, tone: 'accent', label: undefined },
)
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
  font-size: max(10px, calc(var(--size) * 0.34));
  font-weight: 600;
  color: var(--color-accent-text);
  background: var(--color-accent-soft);
}
.app-monogram--square {
  border-radius: 8px;
}
.app-monogram--brand {
  color: rgb(var(--v-theme-brand));
  background: rgba(var(--v-theme-brand), 0.14);
}
</style>
