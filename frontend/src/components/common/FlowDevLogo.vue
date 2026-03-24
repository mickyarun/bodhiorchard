<template>
  <div class="d-flex align-center ga-2">
    <v-icon
      icon="mdi-tree-outline"
      color="primary"
      :size="size"
    />
    <span class="font-weight-bold" :class="titleClass" style="letter-spacing: -0.5px;">
      <span class="text-primary">Bodhi</span><span class="text-on-background">grove</span>
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  size?: number
}>(), {
  size: 32,
})

const titleClass = computed(() => props.size >= 32 ? 'text-h5' : 'text-h6')
</script>
