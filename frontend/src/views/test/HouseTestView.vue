<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { HouseTestEngine } from '@/engine/housetest'

const containerRef = ref<HTMLElement | null>(null)

// Instantiated outside onMounted so onUnmounted can reference it
// without needing to register the hook after an await.
const engine = new HouseTestEngine()
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
  <div ref="containerRef" class="house-test-container" />
</template>

<style scoped>
.house-test-container {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  position: relative;
  background: #87ceeb;
}
</style>
