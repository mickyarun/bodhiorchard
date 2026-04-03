<template>
  <div class="accessory-picker">
    <div class="text-subtitle-1 font-weight-bold mb-3">
      Accessories
    </div>
    <div class="accessory-picker__row">
      <div class="accessory-picker__slot">
        <div class="text-caption text-medium-emphasis mb-1">Right Hand</div>
        <div class="accessory-picker__items">
          <div
            class="accessory-picker__item"
            :class="{ 'accessory-picker__item--active': !rightHand }"
            @click="emit('update', 'rightHand', '')"
          >
            <v-icon icon="mdi-close" size="20" />
            <span class="text-caption">None</span>
          </div>
          <div
            v-for="acc in rightHandItems"
            :key="acc.id"
            class="accessory-picker__item"
            :class="{
              'accessory-picker__item--active': rightHand === acc.id,
              'accessory-picker__item--locked': acc.locked,
            }"
            @click="!acc.locked && emit('update', 'rightHand', acc.id)"
          >
            <v-icon :icon="acc.locked ? 'mdi-lock' : acc.icon" size="20" />
            <span class="text-caption">{{ acc.name }}</span>
          </div>
        </div>
      </div>
      <div class="accessory-picker__slot">
        <div class="text-caption text-medium-emphasis mb-1">Left Hand</div>
        <div class="accessory-picker__items">
          <div
            class="accessory-picker__item"
            :class="{ 'accessory-picker__item--active': !leftHand }"
            @click="emit('update', 'leftHand', '')"
          >
            <v-icon icon="mdi-close" size="20" />
            <span class="text-caption">None</span>
          </div>
          <div
            v-for="acc in leftHandItems"
            :key="acc.id"
            class="accessory-picker__item"
            :class="{
              'accessory-picker__item--active': leftHand === acc.id,
              'accessory-picker__item--locked': acc.locked,
            }"
            @click="!acc.locked && emit('update', 'leftHand', acc.id)"
          >
            <v-icon :icon="acc.locked ? 'mdi-lock' : acc.icon" size="20" />
            <span class="text-caption">{{ acc.name }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { getAccessoriesWithUnlocks, getAccessoriesForSlot } from '@/engine/characters/KayKitManifest'
import { useXPStore } from '@/stores/xp'

defineProps<{
  rightHand: string
  leftHand: string
}>()

const emit = defineEmits<{
  (e: 'update', key: 'rightHand' | 'leftHand', value: string): void
}>()

const xpStore = useXPStore()

const rightHandItems = computed(() => {
  const unlocked = xpStore.profile?.unlocked_accessories
  if (unlocked) return getAccessoriesWithUnlocks('right_hand', new Set(unlocked))
  return getAccessoriesForSlot('right_hand')
})

const leftHandItems = computed(() => {
  const unlocked = xpStore.profile?.unlocked_accessories
  if (unlocked) return getAccessoriesWithUnlocks('left_hand', new Set(unlocked))
  return getAccessoriesForSlot('left_hand')
})
</script>

<style scoped>
.accessory-picker__row {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}

.accessory-picker__slot {
  flex: 1;
  min-width: 150px;
}

.accessory-picker__items {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.accessory-picker__item {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 8px 12px;
  border: 2px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
  min-width: 72px;
}

.accessory-picker__item:hover:not(.accessory-picker__item--locked) {
  border-color: rgba(255, 255, 255, 0.3);
  transform: translateY(-2px);
  box-shadow: 0 3px 10px rgba(0, 0, 0, 0.25);
}

.accessory-picker__item--active {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.12);
  box-shadow: 0 0 0 2px rgba(46, 125, 50, 0.25);
}

.accessory-picker__item--locked {
  opacity: 0.35;
  cursor: not-allowed;
}
</style>
