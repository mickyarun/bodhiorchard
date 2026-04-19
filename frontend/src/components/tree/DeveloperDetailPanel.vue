<template>
  <v-card class="dev-detail-panel" elevation="8" rounded="lg">
    <!-- Header -->
    <div class="d-flex align-center px-4 pt-3 pb-1">
      <v-avatar size="32" :color="info.isAgent ? 'blue-lighten-4' : 'purple-lighten-4'" class="mr-2">
        <v-img v-if="member?.avatar_url" :src="member.avatar_url" />
        <v-icon v-else :icon="info.isAgent ? 'mdi-robot' : 'mdi-account'" size="20" />
      </v-avatar>
      <div class="flex-grow-1 overflow-hidden">
        <div class="text-subtitle-1 font-weight-bold text-truncate">
          {{ info.name }}
        </div>
        <div class="text-caption text-medium-emphasis text-truncate">
          {{ cleanModelName }}
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
      <v-chip
        :color="info.isAgent ? 'blue' : 'purple'"
        size="x-small"
        variant="tonal"
      >
        {{ info.isAgent ? 'AI Agent' : 'Developer' }}
      </v-chip>
      <v-chip
        v-if="info.careMode"
        :color="info.careMode === 'water' ? 'cyan' : 'brown'"
        size="x-small"
        variant="tonal"
        :prepend-icon="info.careMode === 'water' ? 'mdi-watering-can' : 'mdi-sack'"
      >
        {{ info.careMode === 'water' ? 'Watering' : 'Fertilizing' }}
      </v-chip>
    </div>

    <v-divider />

    <!-- Scrollable content -->
    <div class="dev-detail-panel__content">
      <!-- Skills / Top Modules -->
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

      <v-divider v-if="member" />

      <!-- Care Activity -->
      <div v-if="member" class="pa-3">
        <div class="text-overline text-medium-emphasis mb-1">
          Care Activity
        </div>
        <div class="d-flex align-center ga-2">
          <v-progress-linear
            :model-value="member.care_pct"
            color="green"
            height="8"
            rounded
            class="flex-grow-1"
          />
          <span class="text-body-2 font-weight-medium">{{ member.care_pct }}%</span>
        </div>
      </div>

      <v-divider />

      <!-- Current Animation -->
      <div class="pa-3">
        <div class="text-overline text-medium-emphasis mb-1">
          Animation
        </div>
        <div v-if="currentClip" class="d-flex align-center ga-2 mb-2">
          <v-icon icon="mdi-play-circle" color="green" size="18" />
          <span class="text-body-2 font-weight-medium">{{ currentClip }}</span>
        </div>
        <v-btn
          v-if="info.clipNames.length > 0"
          size="small"
          variant="tonal"
          color="primary"
          prepend-icon="mdi-shuffle"
          @click="onPlayRandom"
        >
          Play Random
        </v-btn>
        <div v-if="info.clipNames.length === 0" class="text-body-2 text-disabled">
          No animations available
        </div>
      </div>

      <v-divider v-if="info.clipNames.length > 0" />

      <!-- Available Clips -->
      <div v-if="info.clipNames.length > 0" class="pa-3">
        <div class="text-overline text-medium-emphasis mb-1">
          Available Clips ({{ info.clipNames.length }})
        </div>
        <div class="d-flex flex-wrap ga-1">
          <v-chip
            v-for="clip in info.clipNames"
            :key="clip"
            size="x-small"
            variant="outlined"
            :color="clip === currentClip ? 'green' : undefined"
          >
            {{ clip }}
          </v-chip>
        </div>
      </div>

      <!-- Contact Info -->
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
import { computed, ref } from 'vue'
import type { CharacterInfo } from './types'

const props = defineProps<{
  info: CharacterInfo
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'play-random'): void
}>()

const member = computed(() => props.info.member)
const currentClip = ref<string | null>(null)

const cleanModelName = computed(() =>
  props.info.modelName
    .replace(/\.(glb|gltf)$/, '')
    .replace(/_/g, ' '),
)

function onPlayRandom(): void {
  emit('play-random')
}

/** Called by parent to update the displayed clip name */
function setCurrentClip(name: string | null): void {
  currentClip.value = name
}

defineExpose({ setCurrentClip })
</script>

<style scoped>
.dev-detail-panel {
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

.dev-detail-panel__content {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}
</style>
