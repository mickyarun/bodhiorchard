<template>
  <div class="character-grid">
    <div class="text-subtitle-1 font-weight-bold mb-3">
      Choose Your Character
    </div>
    <div class="character-grid__items">
      <v-tooltip
        v-for="char in characters"
        :key="char.id"
        :text="char.locked ? `Reach ${char.unlockName} (Lv.${char.unlockLevel}) to unlock` : char.name"
        location="top"
      >
        <template #activator="{ props: tooltipProps }">
          <div
            v-bind="tooltipProps"
            class="character-grid__card"
            :class="{
              'character-grid__card--selected': char.id === selectedId,
              'character-grid__card--locked': char.locked,
            }"
            @click="!char.locked && emit('select', char.id)"
          >
            <img
              :src="'/' + char.thumbnail"
              :alt="char.name"
              class="character-grid__img"
            >
            <div class="character-grid__name">
              {{ char.name }}
            </div>
            <!-- Lock overlay with level badge -->
            <div
              v-if="char.locked"
              class="character-grid__lock-overlay"
            >
              <v-icon icon="mdi-lock" size="28" />
              <v-chip
                size="x-small"
                color="warning"
                variant="flat"
                class="character-grid__level-badge"
              >
                Lv.{{ char.unlockLevel }}
              </v-chip>
            </div>
          </div>
        </template>
      </v-tooltip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { getCharactersWithUnlocks, getAllCharacters, type KayKitCharacterDef } from '@/engine/characters/KayKitManifest'
import { useXPStore } from '@/stores/xp'

defineProps<{
  selectedId: string
}>()

const emit = defineEmits<{
  (e: 'select', id: string): void
}>()

const xpStore = useXPStore()

const characters = computed<KayKitCharacterDef[]>(() => {
  const unlocked = xpStore.profile?.unlocked_characters
  if (unlocked) {
    return getCharactersWithUnlocks(new Set(unlocked))
  }
  return [...getAllCharacters()]
})
</script>

<style scoped>
.character-grid__items {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
}

.character-grid__card {
  position: relative;
  border: 2px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  padding: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
  background: rgba(255, 255, 255, 0.04);
  text-align: center;
}

.character-grid__card:hover:not(.character-grid__card--locked) {
  border-color: rgba(255, 255, 255, 0.3);
  transform: translateY(-3px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.character-grid__card--selected {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.12);
  box-shadow: 0 0 0 3px rgba(46, 125, 50, 0.3);
  transform: scale(1.03);
}

.character-grid__card--locked {
  cursor: not-allowed;
}

.character-grid__card--locked .character-grid__img {
  filter: grayscale(1) brightness(0.5);
}

.character-grid__card--locked .character-grid__name {
  opacity: 0.5;
}

.character-grid__img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: contain;
  border-radius: 8px;
  transition: filter 0.2s ease;
}

.character-grid__name {
  font-size: 13px;
  font-weight: 500;
  margin-top: 4px;
  transition: opacity 0.2s;
}

.character-grid__lock-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  color: rgba(255, 255, 255, 0.7);
}

.character-grid__level-badge {
  font-size: 10px !important;
  font-weight: 700;
}
</style>
