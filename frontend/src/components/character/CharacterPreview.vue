<template>
  <div
    ref="containerRef"
    class="character-preview"
  >
    <!-- Skeleton loader before PlayCanvas boots -->
    <v-skeleton-loader
      v-if="!sceneReady"
      type="image"
      class="character-preview__skeleton"
    />
    <!-- Spinner during character swap (scene already running) -->
    <transition name="fade">
      <div
        v-if="sceneReady && loading"
        class="character-preview__loading"
      >
        <v-progress-circular
          indeterminate
          size="28"
          width="3"
          color="primary"
        />
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import type { CharacterConfig } from '@/engine/characters/CharacterConfig'
import { CharacterPreviewScene } from '@/engine/characters/CharacterPreviewScene'

const props = defineProps<{
  config: CharacterConfig
  /** Which KayKit emote to drive the character with while displayed.
   *  0 = idle, 1 = wave, 2 = cheer, 3 = defeat.
   *  Defaults to idle when unspecified. */
  emote?: 0 | 1 | 2 | 3
}>()

const containerRef = ref<HTMLElement | null>(null)
const sceneReady = ref(false)
const loading = ref(true)
let scene: CharacterPreviewScene | null = null
let resizeObserver: ResizeObserver | null = null

onMounted(async () => {
  if (!containerRef.value) return

  scene = new CharacterPreviewScene()
  await scene.init(containerRef.value)
  sceneReady.value = true  // scene boots with lighting + pedestal visible

  await scene.setCharacter(props.config)
  scene.setEmote(props.emote ?? 0)
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
    scene.setEmote(props.emote ?? 0)
    loading.value = false
  },
  { deep: true },
)

// Hot-swap the emote without reloading the GLB — cheap, no flicker.
watch(
  () => props.emote,
  (next) => {
    scene?.setEmote(next ?? 0)
  },
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
  background: rgba(0, 0, 0, 0.3);
}

.character-preview :deep(canvas) {
  display: block;
}

.character-preview__skeleton {
  position: absolute;
  inset: 0;
  z-index: 1;
}

.character-preview__loading {
  position: absolute;
  bottom: 16px;
  right: 16px;
  z-index: 2;
}

/* Fade transition for swap spinner */
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
</style>
