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

<!-- Reveals slotted content as it scrolls into view, via IntersectionObserver.
     SSR-safe: the server renders the content fully visible (no hidden state in
     markup), so crawlers and no-JS users see everything. The hidden→reveal
     transition is added only after mount, and is skipped entirely under
     prefers-reduced-motion. -->
<template>
  <div ref="root" class="scroll-reveal" :class="{ 'scroll-reveal--armed': armed, 'scroll-reveal--in': shown }">
    <slot />
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    // Stagger delay in ms, for sequencing sibling reveals.
    delay?: number
  }>(),
  { delay: 0 },
)

const root = ref<HTMLElement | null>(null)
const armed = ref(false)
const shown = ref(false)
let observer: IntersectionObserver | null = null

onMounted(() => {
  const el = root.value
  if (!el) return

  const prefersReduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  if (prefersReduced || typeof IntersectionObserver === 'undefined') {
    shown.value = true
    return
  }

  // Arm the hidden state only now (post-SSR) so markup ships visible.
  armed.value = true
  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          shown.value = true
          observer?.disconnect()
        }
      }
    },
    { threshold: 0.12, rootMargin: '0px 0px -8% 0px' },
  )
  observer.observe(el)
})

onBeforeUnmount(() => observer?.disconnect())
</script>

<style scoped>
.scroll-reveal--armed {
  opacity: 0;
  transform: translateY(18px);
  transition:
    opacity var(--dur-long, 360ms) var(--ease-out, cubic-bezier(0.16, 1, 0.3, 1)),
    transform var(--dur-long, 360ms) var(--ease-out, cubic-bezier(0.16, 1, 0.3, 1));
  transition-delay: v-bind('`${props.delay}ms`');
}
.scroll-reveal--in {
  opacity: 1;
  transform: none;
}
</style>
