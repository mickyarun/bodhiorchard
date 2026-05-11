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

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { TreeTestEngine } from '@/engine/treetest'

const containerRef = ref<HTMLElement | null>(null)

// Instantiated outside onMounted so onUnmounted can reference it
// without needing to register the hook after an await.
const engine = new TreeTestEngine()
let observer: ResizeObserver | null = null

// MUST be registered before the first await — Vue loses the active component
// instance context after any await in setup(), so lifecycle hooks registered
// after an await silently fail.
onUnmounted(() => {
  observer?.disconnect()
  observer = null
  engine.destroy()
})

onMounted(async () => {
  if (!containerRef.value) return

  const rect = containerRef.value.getBoundingClientRect()
  await engine.init(containerRef.value, rect.width, rect.height)

  observer = new ResizeObserver((entries) => {
    for (const entry of entries) {
      const { width, height } = entry.contentRect
      engine.resize(width, height)
    }
  })
  observer.observe(containerRef.value)
})
</script>

<template>
  <div ref="containerRef" class="tree-test-container" />
</template>

<style scoped>
.tree-test-container {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  position: relative;
  background: #1a1a2e;
}
</style>
