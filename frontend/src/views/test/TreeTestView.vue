<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { TreeTestEngine } from '@/engine/treetest'

const containerRef = ref<HTMLElement | null>(null)
let engine: TreeTestEngine | null = null

onMounted(async () => {
  if (!containerRef.value) return

  engine = new TreeTestEngine()
  const rect = containerRef.value.getBoundingClientRect()
  await engine.init(containerRef.value, rect.width, rect.height)

  // Handle resize
  const observer = new ResizeObserver((entries) => {
    for (const entry of entries) {
      const { width, height } = entry.contentRect
      engine?.resize(width, height)
    }
  })
  observer.observe(containerRef.value)

  onUnmounted(() => {
    observer.disconnect()
    engine?.destroy()
    engine = null
  })
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
