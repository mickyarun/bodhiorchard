<template>
  <v-card class="tree-legend pa-3" elevation="2" max-width="220">
    <div class="text-caption font-weight-bold mb-2">Garden Legend</div>

    <div class="text-caption font-weight-bold text-medium-emphasis mt-1 mb-1">Tree Size</div>
    <div v-for="item in treeSizes" :key="item.label" class="d-flex align-center ga-2 mb-1">
      <v-icon :icon="item.icon" size="14" :color="item.color" />
      <span class="text-caption">{{ item.label }}</span>
    </div>

    <div class="text-caption font-weight-bold text-medium-emphasis mt-2 mb-1">Features</div>
    <div v-for="item in features" :key="item.label" class="d-flex align-center ga-2 mb-1">
      <span class="legend-dot" :style="{ backgroundColor: item.color }" />
      <span class="text-caption">{{ item.label }}</span>
    </div>

    <div class="text-caption font-weight-bold text-medium-emphasis mt-2 mb-1">Bugs</div>
    <div v-for="item in bugs" :key="item.label" class="d-flex align-center ga-2 mb-1">
      <span class="legend-dot legend-dot--square" :style="{ backgroundColor: item.color }" />
      <span class="text-caption">{{ item.label }}</span>
    </div>

    <div class="text-caption font-weight-bold text-medium-emphasis mt-2 mb-1">Characters</div>
    <div v-for="item in characters" :key="item.label" class="d-flex align-center ga-2 mb-1">
      <v-icon :icon="item.icon" size="14" :color="item.color" />
      <span class="text-caption">{{ item.label }}</span>
    </div>
  </v-card>
</template>

<script setup lang="ts">
const treeSizes = [
  { icon: 'mdi-sprout', color: 'green-lighten-2', label: 'Sprout (new repo)' },
  { icon: 'mdi-tree-outline', color: 'green-lighten-1', label: 'Sapling (< 90 days)' },
  { icon: 'mdi-tree', color: 'green', label: 'Medium (< 1 year)' },
  { icon: 'mdi-tree', color: 'green-darken-2', label: 'Mature (1+ years)' },
]

const features = [
  { color: '#FF8F00', label: 'Released (fruit)' },
  { color: '#CE93D8', label: 'In Review (flower)' },
  { color: '#F48FB1', label: 'Ready (bloom)' },
]

const bugs = [
  { color: '#FFC107', label: 'Low severity' },
  { color: '#FF9800', label: 'Medium severity' },
  { color: '#F44336', label: 'High severity' },
  { color: '#B71C1C', label: 'Critical severity' },
]

const characters = [
  { icon: 'mdi-account', color: 'purple', label: 'Developer' },
  { icon: 'mdi-robot', color: 'grey-darken-3', label: 'AI Agent (MIB)' },
]
</script>

<style scoped>
.tree-legend {
  position: absolute;
  bottom: 16px;
  right: 16px;
  z-index: 50;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-dot--square {
  border-radius: 2px;
}
</style>
