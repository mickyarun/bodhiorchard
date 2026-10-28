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

<!-- A person's photo, or their initials on a tonal wash. Decorative by
     default: the name is usually written beside it, so it stays out of the
     accessibility tree. Pass ``label`` when it stands alone and must be
     announced. ``src`` is the stored ``avatar_url``; a missing or broken
     photo (a Slack link can rot) falls back to the initials.
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
  >
    <img
      v-if="photo && !failed"
      :src="photo"
      alt=""
      class="app-monogram__photo"
      referrerpolicy="no-referrer"
      @error="failed = true"
    />
    <template v-else>{{ initialsOf(name || '?') }}</template>
  </span>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { initialsOf, resolveAvatarUrl } from '@/utils/avatar'

const props = withDefaults(
  defineProps<{
    name: string | null | undefined
    src?: string | null
    size?: number
    square?: boolean
    tone?: 'accent' | 'brand'
    label?: string
  }>(),
  { src: null, size: 32, square: false, tone: 'accent', label: undefined },
)

const photo = computed(() => resolveAvatarUrl(props.src))
const failed = ref(false)
// A new URL (a replaced photo) deserves a fresh attempt.
watch(photo, () => {
  failed.value = false
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
  overflow: hidden;
  font-size: max(10px, calc(var(--size) * 0.34));
  font-weight: 600;
  color: var(--color-accent-text);
  background: var(--color-accent-soft);
}
.app-monogram__photo {
  width: 100%;
  height: 100%;
  border-radius: inherit;
  object-fit: cover;
}
.app-monogram--square {
  border-radius: 8px;
}
.app-monogram--brand {
  color: rgb(var(--v-theme-brand));
  background: rgba(var(--v-theme-brand), 0.14);
}
</style>
