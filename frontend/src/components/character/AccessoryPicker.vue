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
            :class="{ 'accessory-picker__item--active': rightHand === acc.id }"
            @click="emit('update', 'rightHand', acc.id)"
          >
            <v-icon icon="mdi-sword" size="20" />
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
            :class="{ 'accessory-picker__item--active': leftHand === acc.id }"
            @click="emit('update', 'leftHand', acc.id)"
          >
            <v-icon icon="mdi-shield" size="20" />
            <span class="text-caption">{{ acc.name }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { getAccessoriesForSlot } from '@/engine/characters/KayKitManifest'

defineProps<{
  rightHand: string
  leftHand: string
}>()

const emit = defineEmits<{
  (e: 'update', key: 'rightHand' | 'leftHand', value: string): void
}>()

const rightHandItems = getAccessoriesForSlot('right_hand')
const leftHandItems = getAccessoriesForSlot('left_hand')
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
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 6px 10px;
  border: 2px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.15s, transform 0.15s;
  min-width: 60px;
}

.accessory-picker__item:hover {
  border-color: rgba(255, 255, 255, 0.3);
  transform: translateY(-1px);
}

.accessory-picker__item--active {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.1);
}
</style>
