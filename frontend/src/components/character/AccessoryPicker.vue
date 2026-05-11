<!--
 * Copyright 2025-2026 Arun Rajkumar
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 -->

<template>
  <div class="accessory-picker">
    <div class="text-subtitle-1 font-weight-bold mb-3">
      Accessories
    </div>
    <div class="accessory-picker__row">
      <div class="accessory-picker__slot">
        <div class="text-caption text-medium-emphasis mb-2">Right Hand</div>
        <div class="accessory-picker__items">
          <div
            class="accessory-picker__card accessory-picker__card--none"
            :class="{ 'accessory-picker__card--selected': !rightHand }"
            @click="emit('update', 'rightHand', '')"
          >
            <div class="accessory-picker__preview">
              <v-icon icon="mdi-close" size="36" />
            </div>
            <div class="accessory-picker__name">None</div>
          </div>
          <v-tooltip
            v-for="acc in rightHandItems"
            :key="acc.id"
            :text="acc.locked ? `Reach Lv.${acc.unlockLevel} to unlock` : acc.name"
            location="top"
          >
            <template #activator="{ props: tp }">
              <div
                v-bind="tp"
                class="accessory-picker__card"
                :class="{
                  'accessory-picker__card--selected': rightHand === acc.id,
                  'accessory-picker__card--locked': acc.locked,
                }"
                @click="!acc.locked && emit('update', 'rightHand', acc.id)"
              >
                <div class="accessory-picker__preview">
                  <v-icon :icon="acc.icon" size="36" />
                </div>
                <div class="accessory-picker__name">{{ acc.name }}</div>
                <div
                  v-if="acc.locked"
                  class="accessory-picker__lock-overlay"
                >
                  <v-icon icon="mdi-lock" size="24" />
                  <v-chip
                    size="x-small"
                    color="warning"
                    variant="flat"
                    class="accessory-picker__level-badge"
                  >
                    Lv.{{ acc.unlockLevel }}
                  </v-chip>
                </div>
              </div>
            </template>
          </v-tooltip>
        </div>
      </div>
      <div class="accessory-picker__slot">
        <div class="text-caption text-medium-emphasis mb-2">Left Hand</div>
        <div class="accessory-picker__items">
          <div
            class="accessory-picker__card accessory-picker__card--none"
            :class="{ 'accessory-picker__card--selected': !leftHand }"
            @click="emit('update', 'leftHand', '')"
          >
            <div class="accessory-picker__preview">
              <v-icon icon="mdi-close" size="36" />
            </div>
            <div class="accessory-picker__name">None</div>
          </div>
          <v-tooltip
            v-for="acc in leftHandItems"
            :key="acc.id"
            :text="acc.locked ? `Reach Lv.${acc.unlockLevel} to unlock` : acc.name"
            location="top"
          >
            <template #activator="{ props: tp }">
              <div
                v-bind="tp"
                class="accessory-picker__card"
                :class="{
                  'accessory-picker__card--selected': leftHand === acc.id,
                  'accessory-picker__card--locked': acc.locked,
                }"
                @click="!acc.locked && emit('update', 'leftHand', acc.id)"
              >
                <div class="accessory-picker__preview">
                  <v-icon :icon="acc.icon" size="36" />
                </div>
                <div class="accessory-picker__name">{{ acc.name }}</div>
                <div
                  v-if="acc.locked"
                  class="accessory-picker__lock-overlay"
                >
                  <v-icon icon="mdi-lock" size="24" />
                  <v-chip
                    size="x-small"
                    color="warning"
                    variant="flat"
                    class="accessory-picker__level-badge"
                  >
                    Lv.{{ acc.unlockLevel }}
                  </v-chip>
                </div>
              </div>
            </template>
          </v-tooltip>
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
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(78px, 1fr));
  gap: 8px;
}

.accessory-picker__card {
  position: relative;
  border: 2px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  padding: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  background: rgba(255, 255, 255, 0.04);
  text-align: center;
}

.accessory-picker__card:hover:not(.accessory-picker__card--locked) {
  border-color: rgba(255, 255, 255, 0.3);
  transform: translateY(-2px);
  box-shadow: 0 3px 10px rgba(0, 0, 0, 0.25);
}

.accessory-picker__card--selected {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.12);
  box-shadow: 0 0 0 2px rgba(46, 125, 50, 0.25);
}

.accessory-picker__card--locked {
  cursor: not-allowed;
}

.accessory-picker__card--locked .accessory-picker__preview,
.accessory-picker__card--locked .accessory-picker__name {
  opacity: 0.35;
  filter: grayscale(1);
}

.accessory-picker__preview {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.2);
  transition: filter 0.2s ease, opacity 0.2s ease;
}

.accessory-picker__name {
  font-size: 11px;
  font-weight: 500;
  margin-top: 4px;
  line-height: 1.2;
  transition: opacity 0.2s;
}

.accessory-picker__lock-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  color: rgba(255, 255, 255, 0.75);
  pointer-events: none;
}

.accessory-picker__level-badge {
  font-size: 9px !important;
  font-weight: 700;
  height: 16px !important;
  padding: 0 6px !important;
}
</style>
