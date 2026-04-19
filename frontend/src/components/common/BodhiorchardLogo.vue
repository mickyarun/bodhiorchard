<template>
  <div class="d-flex align-center ga-2">
    <img
      :src="logoSrc"
      :width="size"
      :height="size"
      alt="Bodhiorchard"
      class="bodhiorchard-logo"
    />
    <span v-if="showText" class="font-weight-bold" :class="titleClass" style="letter-spacing: -0.5px;">
      <span class="text-primary">Bodhi</span><span class="text-on-background">orchard</span>
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  size?: number
  showText?: boolean
}>(), {
  size: 32,
  showText: true,
})

const logoSrc = computed(() =>
  props.size <= 64
    ? '/assets/bodhiorchard-logo-sm.png'
    : '/assets/bodhiorchard-logo.png'
)

const titleClass = computed(() => props.size >= 32 ? 'text-h5' : 'text-h6')
</script>

<style scoped>
.bodhiorchard-logo {
  border-radius: 50%;
  object-fit: contain;
}
</style>
