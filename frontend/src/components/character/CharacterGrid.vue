<template>
  <div class="character-grid">
    <div class="text-subtitle-1 font-weight-bold mb-3">
      Choose Your Character
    </div>
    <div class="character-grid__items">
      <div
        v-for="char in characters"
        :key="char.id"
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
        <v-icon
          v-if="char.locked"
          class="character-grid__lock"
          icon="mdi-lock"
          size="24"
        />
      </div>
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
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 12px;
}

.character-grid__card {
  position: relative;
  border: 2px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  padding: 8px;
  cursor: pointer;
  transition: border-color 0.2s, transform 0.15s;
  background: rgba(255, 255, 255, 0.04);
  text-align: center;
}

.character-grid__card:hover:not(.character-grid__card--locked) {
  border-color: rgba(255, 255, 255, 0.3);
  transform: translateY(-2px);
}

.character-grid__card--selected {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.1);
}

.character-grid__card--locked {
  opacity: 0.4;
  cursor: not-allowed;
}

.character-grid__img {
  width: 100%;
  aspect-ratio: 1;
  object-fit: contain;
  border-radius: 8px;
}

.character-grid__name {
  font-size: 13px;
  font-weight: 500;
  margin-top: 4px;
}

.character-grid__lock {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: rgba(255, 255, 255, 0.6);
}
</style>
