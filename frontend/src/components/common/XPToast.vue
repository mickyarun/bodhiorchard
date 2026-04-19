<template>
  <div class="xp-toast-container">
    <transition-group name="toast-slide">
      <v-snackbar
        v-for="toast in toasts"
        :key="toast.id"
        :model-value="true"
        :color="toast.type === 'level_up' ? 'warning' : toast.type === 'sp_awarded' ? 'secondary' : 'surface'"
        :timeout="-1"
        location="bottom right"
        variant="flat"
        rounded="lg"
        class="xp-toast"
        :class="{ 'xp-toast--levelup': toast.type === 'level_up' }"
        @update:model-value="dismissToast(toast.id)"
      >
        <div class="d-flex align-center ga-3">
          <!-- Source icon -->
          <v-icon
            :icon="getSourceIcon(toast.source)"
            :color="toast.type === 'level_up' ? 'white' : 'primary'"
            :size="toast.type === 'level_up' ? 28 : 22"
          />
          <div>
            <!-- Normal XP award -->
            <template v-if="toast.type === 'xp_awarded'">
              <span class="text-body-2 font-weight-bold">
                +{{ toast.xpAmount }} XP
              </span>
              <span class="text-caption text-medium-emphasis ml-1">
                — {{ getSourceLabel(toast.source) }}
              </span>
            </template>
            <!-- SP award (fractional amounts supported) -->
            <template v-else-if="toast.type === 'sp_awarded'">
              <span class="text-body-2 font-weight-bold">
                +{{ formatSP(toast.xpAmount) }} SP
              </span>
              <span class="text-caption text-medium-emphasis ml-1">
                — {{ getSourceLabel(toast.source) }}
              </span>
            </template>
            <!-- Level up celebration -->
            <template v-else-if="toast.type === 'level_up'">
              <div class="text-body-1 font-weight-bold">
                Level Up! {{ LEVEL_ICONS[toast.levelName || ''] }} Lv.{{ toast.level }}
              </div>
              <div class="text-caption text-capitalize">
                {{ (toast.levelName || '').replace('_', ' ') }}
              </div>
            </template>
          </div>
        </div>

        <template #actions>
          <v-btn
            variant="text"
            size="small"
            icon="mdi-close"
            @click="dismissToast(toast.id)"
          />
        </template>
      </v-snackbar>
    </transition-group>
  </div>
</template>

<script setup lang="ts">
import { type XPToastItem, getSourceLabel, getSourceIcon } from '@/composables/useXPSocket'

defineProps<{
  toasts: XPToastItem[]
}>()

const emit = defineEmits<{
  (e: 'dismiss', id: number): void
}>()

function dismissToast(id: number): void {
  emit('dismiss', id)
}

function formatSP(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(2)
}

const LEVEL_ICONS: Record<string, string> = {
  seedling: '🌱',
  sprout: '🌿',
  sapling: '🌲',
  tree: '🌳',
  ancient_oak: '🏔️',
}
</script>

<style scoped>
.xp-toast-container {
  position: fixed;
  bottom: 16px;
  right: 16px;
  z-index: 2000;
  display: flex;
  flex-direction: column-reverse;
  gap: 8px;
  pointer-events: none;
}

.xp-toast {
  pointer-events: auto;
}

.xp-toast--levelup {
  animation: levelup-pulse 0.5s ease-out;
}

@keyframes levelup-pulse {
  0% { transform: scale(0.8); opacity: 0; }
  50% { transform: scale(1.05); }
  100% { transform: scale(1); opacity: 1; }
}

.toast-slide-enter-active {
  transition: all 0.3s ease-out;
}
.toast-slide-leave-active {
  transition: all 0.2s ease-in;
}
.toast-slide-enter-from {
  transform: translateX(100%);
  opacity: 0;
}
.toast-slide-leave-to {
  transform: translateX(100%);
  opacity: 0;
}
</style>
