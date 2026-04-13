<template>
  <div class="tree-legend">
    <!-- Header — always visible -->
    <div class="legend-header" @click="collapsed = !collapsed">
      <span class="legend-title">Garden Legend</span>
      <v-icon
        :icon="collapsed ? 'mdi-chevron-up' : 'mdi-chevron-down'"
        size="14"
        class="legend-toggle"
      />
    </div>

    <!-- Body — collapsed when minimized -->
    <div v-if="!collapsed" class="legend-body">
      <div class="legend-section-label">Tree Size</div>
      <div v-for="item in treeSizes" :key="item.label" class="legend-row">
        <v-icon :icon="item.icon" size="13" :color="item.color" />
        <span>{{ item.label }}</span>
      </div>

      <div class="legend-section-label mt">Features</div>
      <div v-for="item in features" :key="item.label" class="legend-row">
        <span class="dot" :style="{ backgroundColor: item.color }" />
        <span>{{ item.label }}</span>
      </div>

      <div class="legend-section-label mt">Bugs</div>
      <div v-for="item in bugs" :key="item.label" class="legend-row">
        <span class="dot dot--square" :style="{ backgroundColor: item.color }" />
        <span>{{ item.label }}</span>
      </div>

      <div class="legend-section-label mt">Characters</div>
      <div v-for="item in characters" :key="item.label" class="legend-row">
        <v-icon :icon="item.icon" size="13" :color="item.color" />
        <span>{{ item.label }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

const STORAGE_KEY = 'bodhigrove_legend_collapsed'
const collapsed = ref(localStorage.getItem(STORAGE_KEY) === 'true')

watch(collapsed, (v) => localStorage.setItem(STORAGE_KEY, String(v)))

const treeSizes = [
  { icon: 'mdi-sprout',       color: 'green-lighten-2', label: 'Small (few features)' },
  { icon: 'mdi-tree-outline', color: 'green-lighten-1', label: 'Medium (some features)' },
  { icon: 'mdi-tree',         color: 'green',           label: 'Large (many features)' },
  { icon: 'mdi-tree',         color: 'green-darken-2',  label: 'Unique color per repo' },
]

const features = [
  { color: '#4CAF50', label: 'Implemented (with leaves)' },
  { color: '#FF9800', label: 'In Progress (bare tree)' },
  { color: '#90CAF9', label: 'Planned (bare tree)' },
]

const bugs = [
  { color: '#FFC107', label: 'Low severity' },
  { color: '#FF9800', label: 'Medium severity' },
  { color: '#F44336', label: 'High severity' },
  { color: '#B71C1C', label: 'Critical severity' },
]

const characters = [
  { icon: 'mdi-account', color: 'purple',       label: 'Developer' },
  { icon: 'mdi-robot',   color: 'grey-darken-3', label: 'AI Agent (MIB)' },
]
</script>

<style scoped>
.tree-legend {
  position: absolute;
  bottom: 16px;
  right: 16px;
  z-index: 50;
  min-width: 190px;
  border-radius: 10px;
  background: rgba(15, 20, 30, 0.45);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.10);
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.25);
  overflow: hidden;
}

.legend-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px 6px;
  cursor: pointer;
  user-select: none;
}

.legend-header:hover {
  background: rgba(255, 255, 255, 0.05);
}

.legend-title {
  font-size: 11px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.90);
  letter-spacing: 0.4px;
  text-transform: uppercase;
}

.legend-toggle {
  opacity: 0.55;
}

.legend-body {
  padding: 0 10px 10px;
}

.legend-section-label {
  font-size: 10px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.45);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}

.legend-section-label.mt {
  margin-top: 10px;
}

.legend-row {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 3px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.80);
}

.dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot--square {
  border-radius: 2px;
}
</style>
