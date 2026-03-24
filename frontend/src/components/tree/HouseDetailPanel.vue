<template>
  <v-card class="house-detail-panel" elevation="8" rounded="lg">
    <!-- Header -->
    <div class="d-flex align-center px-4 pt-3 pb-1">
      <v-avatar size="32" color="brown-lighten-4" class="mr-2">
        <v-img v-if="member?.avatar_url" :src="member.avatar_url" />
        <v-icon v-else icon="mdi-home" size="20" />
      </v-avatar>
      <div class="flex-grow-1 overflow-hidden">
        <div class="text-subtitle-1 font-weight-bold text-truncate">
          {{ houseInfo.name }}
        </div>
        <div class="text-caption text-medium-emphasis">
          Developer Village
        </div>
      </div>
      <v-spacer />
      <v-btn
        icon="mdi-close"
        size="x-small"
        variant="text"
        @click="emit('close')"
      />
    </div>

    <div class="d-flex align-center ga-1 px-4 pb-2">
      <!-- Activity chip -->
      <v-chip
        :color="activityColor"
        size="x-small"
        variant="tonal"
        :prepend-icon="activityIcon"
      >
        {{ activityLabel }}
      </v-chip>

      <!-- Presence badge -->
      <v-chip
        v-if="member?.presence"
        color="grey"
        size="x-small"
        variant="tonal"
        prepend-icon="mdi-circle-small"
      >
        {{ presenceLabel }}
      </v-chip>
    </div>

    <v-divider />

    <!-- Content -->
    <div class="house-detail-panel__content">
      <!-- Activity Info -->
      <div class="pa-3">
        <div class="text-overline text-medium-emphasis mb-1">
          Status
        </div>
        <div class="text-body-2">
          {{ statusDescription }}
        </div>
      </div>

      <v-divider />

      <!-- Top Modules -->
      <div v-if="member" class="pa-3">
        <div class="text-overline text-medium-emphasis mb-1">
          Skills & Modules
        </div>
        <div class="d-flex flex-wrap ga-1">
          <v-chip
            v-for="mod in member.top_modules"
            :key="mod"
            size="small"
            variant="tonal"
            color="purple"
            prepend-icon="mdi-code-braces"
          >
            {{ mod }}
          </v-chip>
        </div>
        <div v-if="member.top_modules.length === 0" class="text-body-2 text-disabled">
          No module assignments
        </div>
      </div>

      <!-- Contact -->
      <div v-if="member?.email" class="pa-3">
        <v-divider class="mb-3" />
        <div class="text-overline text-medium-emphasis mb-1">
          Contact
        </div>
        <div class="text-body-2 text-medium-emphasis">
          {{ member.email }}
        </div>
      </div>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { HouseInfo, HouseActivity } from './types'
import type { MemberActivity } from '@/types/dashboard'

const props = defineProps<{
  houseInfo: HouseInfo
  member?: MemberActivity
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const activityColor = computed(() => {
  const map: Record<HouseActivity, string> = {
    sleeping: 'indigo',
    home: 'amber',
    away: 'grey',
    coffee_bar: 'brown',
    cafeteria: 'orange',
  }
  return map[props.houseInfo.activity]
})

const activityIcon = computed(() => {
  const map: Record<HouseActivity, string> = {
    sleeping: 'mdi-bed',
    home: 'mdi-home',
    away: 'mdi-briefcase',
    coffee_bar: 'mdi-coffee',
    cafeteria: 'mdi-silverware-fork-knife',
  }
  return map[props.houseInfo.activity]
})

const activityLabel = computed(() => {
  const map: Record<HouseActivity, string> = {
    sleeping: 'Sleeping',
    home: 'At Home',
    away: 'Away',
    coffee_bar: 'At the Café',
    cafeteria: 'At Lunch',
  }
  return map[props.houseInfo.activity]
})

const presenceLabel = computed(() => {
  const map: Record<string, string> = {
    active: 'Active',
    on_break: 'On Break',
    at_home: 'At Home',
  }
  return map[props.member?.presence ?? ''] ?? 'Unknown'
})

const statusDescription = computed(() => {
  const map: Record<HouseActivity, string> = {
    sleeping: 'Currently sleeping. Lights are dimmed and the house is quiet.',
    home: 'At home and active. TV is on and the lights are warm.',
    away: 'Away from home. The house is dark and empty.',
    coffee_bar: 'Grabbing a tea at the Village Café.',
    cafeteria: 'Having lunch at the Village Kitchen.',
  }
  return map[props.houseInfo.activity]
})
</script>

<style scoped>
.house-detail-panel {
  position: absolute;
  top: 8px;
  right: 8px;
  bottom: 8px;
  width: 320px;
  z-index: 20;
  display: flex;
  flex-direction: column;
  background: rgba(var(--v-theme-surface), 0.95) !important;
  backdrop-filter: blur(8px);
}

.house-detail-panel__content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}
</style>
