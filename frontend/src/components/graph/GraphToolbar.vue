<template>
  <div class="graph-toolbar" @wheel.stop @pointerdown.stop @mousedown.stop @click.stop>
    <v-card variant="tonal" class="pa-2 d-flex align-center ga-2 flex-wrap" density="compact">
      <!-- Cross-repo links toggle -->
      <v-btn
        :variant="crossRepo ? 'flat' : 'text'"
        :color="crossRepo ? 'cyan' : undefined"
        size="small"
        prepend-icon="mdi-link-variant"
        @click="toggleCrossRepo"
      >
        Cross-repo
      </v-btn>

      <!-- Bus factor toggle -->
      <v-btn
        :variant="busFactor ? 'flat' : 'text'"
        :color="busFactor ? 'warning' : undefined"
        size="small"
        prepend-icon="mdi-account-alert"
        @click="toggleBusFactor"
      >
        Bus Factor
      </v-btn>

      <!-- Status colors toggle -->
      <v-btn
        :variant="statusColors ? 'flat' : 'text'"
        :color="statusColors ? 'info' : undefined"
        size="small"
        prepend-icon="mdi-palette"
        @click="toggleStatus"
      >
        Status
      </v-btn>

      <!-- Threats toggle -->
      <v-btn
        :variant="threats ? 'flat' : 'text'"
        :color="threats ? 'error' : undefined"
        size="small"
        prepend-icon="mdi-bug"
        @click="toggleThreats"
      >
        Threats
      </v-btn>

      <!-- BUD badges toggle -->
      <v-btn
        :variant="budBadges ? 'flat' : 'text'"
        :color="budBadges ? 'success' : undefined"
        size="small"
        prepend-icon="mdi-seed-outline"
        @click="toggleBudBadges"
      >
        BUD Stage
      </v-btn>

      <v-divider vertical class="mx-1" />

      <!-- Developer filter (searchable, scroll-isolated) -->
      <v-autocomplete
        v-model="selectedDev"
        :items="devItems"
        item-title="name"
        item-value="userId"
        placeholder="Filter by developer"
        density="compact"
        variant="outlined"
        hide-details
        clearable
        class="dev-filter"
        :menu-props="{ maxHeight: 250, class: 'graph-dropdown' }"
        @update:model-value="onDevFilter"
      />
    </v-card>

    <!-- Active status legend -->
    <div v-if="statusColors" class="status-legend mt-2 d-flex ga-2">
      <v-chip size="x-small" color="blue" label>planned</v-chip>
      <v-chip size="x-small" color="orange" label>in progress</v-chip>
      <v-chip size="x-small" color="green" label>implemented</v-chip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface MemberItem {
  userId: string
  name: string
}

const props = defineProps<{
  members: MemberItem[]
}>()

const emit = defineEmits<{
  (e: 'toggle-cross-repo', active: boolean): void
  (e: 'toggle-bus-factor', active: boolean): void
  (e: 'toggle-status', active: boolean): void
  (e: 'toggle-threats', active: boolean): void
  (e: 'toggle-bud-badges', active: boolean): void
  (e: 'filter-developer', userId: string | null): void
}>()

const crossRepo = ref(true)
const busFactor = ref(false)
const statusColors = ref(false)
const threats = ref(false)
const budBadges = ref(false)
const selectedDev = ref<string | null>(null)

const devItems = computed(() => props.members)

function toggleCrossRepo(): void {
  crossRepo.value = !crossRepo.value
  emit('toggle-cross-repo', crossRepo.value)
}

function toggleBusFactor(): void {
  busFactor.value = !busFactor.value
  emit('toggle-bus-factor', busFactor.value)
}

function toggleStatus(): void {
  statusColors.value = !statusColors.value
  emit('toggle-status', statusColors.value)
}

function toggleThreats(): void {
  threats.value = !threats.value
  emit('toggle-threats', threats.value)
}

function toggleBudBadges(): void {
  budBadges.value = !budBadges.value
  emit('toggle-bud-badges', budBadges.value)
}

function onDevFilter(userId: string | null): void {
  emit('filter-developer', userId)
}
</script>

<style scoped>
.graph-toolbar {
  position: absolute;
  bottom: 16px;
  left: 16px;
  z-index: 10;
  max-width: calc(100% - 32px);
}

.dev-filter {
  max-width: 220px;
  min-width: 180px;
}

.status-legend {
  padding-left: 4px;
}
</style>

<!-- Unscoped: stop wheel events on the teleported dropdown overlay -->
<style>
.graph-dropdown .v-list {
  overscroll-behavior: contain;
}
</style>
