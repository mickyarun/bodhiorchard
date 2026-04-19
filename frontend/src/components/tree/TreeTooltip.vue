<template>
  <v-card
    class="tree-tooltip"
    :style="{ left: position.x + 'px', top: position.y + 'px' }"
    elevation="8"
    max-width="240"
  >
    <v-card-text class="pa-3">
      <div v-for="(value, key) in data" :key="String(key)" class="text-body-2">
        <span class="font-weight-medium text-medium-emphasis">{{ key }}:</span>
        {{ value }}
      </div>
    </v-card-text>
  </v-card>
</template>

<script setup lang="ts">
defineProps<{
  data: Record<string, unknown>
  position: { x: number; y: number }
}>()

defineEmits<{
  close: []
}>()
</script>

<style scoped>
.tree-tooltip {
  position: absolute;
  z-index: 100;
  pointer-events: none;
}
</style>
