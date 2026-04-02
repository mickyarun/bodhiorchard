<template>
  <div
    ref="containerRef"
    class="character-preview"
  >
    <div
      v-if="loading"
      class="character-preview__loading"
    >
      <v-progress-circular
        indeterminate
        size="32"
        color="primary"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import type { CharacterConfig } from '@/engine/characters/CharacterConfig'
import { CharacterPreviewScene } from '@/engine/characters/CharacterPreviewScene'

const props = defineProps<{
  config: CharacterConfig
}>()

const containerRef = ref<HTMLElement | null>(null)
const loading = ref(true)
let scene: CharacterPreviewScene | null = null
let resizeObserver: ResizeObserver | null = null

onMounted(async () => {
  if (!containerRef.value) return

  scene = new CharacterPreviewScene()
  await scene.init(containerRef.value)
  await scene.setCharacter(props.config)
  loading.value = false

  resizeObserver = new ResizeObserver(() => {
    if (!containerRef.value || !scene) return
    scene.resize(containerRef.value.clientWidth, containerRef.value.clientHeight)
  })
  resizeObserver.observe(containerRef.value)
})

watch(
  () => props.config,
  async (newConfig) => {
    if (!scene) return
    loading.value = true
    await scene.setCharacter(newConfig)
    loading.value = false
  },
  { deep: true },
)

onUnmounted(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
  scene?.destroy()
  scene = null
})
</script>

<style scoped>
.character-preview {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 300px;
  border-radius: 12px;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.2);
}

.character-preview :deep(canvas) {
  display: block;
}

.character-preview__loading {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  z-index: 1;
}
</style>
