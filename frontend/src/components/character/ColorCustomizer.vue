<template>
  <div class="color-customizer">
    <div class="text-subtitle-1 font-weight-bold mb-3">
      Customize Colors
    </div>
    <div class="color-customizer__row">
      <div
        v-for="item in colorItems"
        :key="item.key"
        class="color-customizer__item"
      >
        <div class="text-caption text-medium-emphasis mb-1">
          {{ item.label }}
        </div>
        <div class="color-customizer__swatches">
          <div
            v-for="swatch in item.swatches"
            :key="swatch"
            class="color-customizer__swatch"
            :class="{ 'color-customizer__swatch--active': currentColors[item.key] === swatch }"
            :style="{ backgroundColor: '#' + swatch }"
            @click="selectColor(item.key, swatch)"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'

type ColorKey = 'shirtColor' | 'pantsColor' | 'skinColor'

const props = defineProps<{
  shirtColor: string
  pantsColor: string
  skinColor: string
}>()

const emit = defineEmits<{
  (e: 'update', key: ColorKey, value: string): void
}>()

const currentColors = reactive<Record<ColorKey, string>>({
  shirtColor: props.shirtColor,
  pantsColor: props.pantsColor,
  skinColor: props.skinColor,
})

watch(() => props.shirtColor, v => { currentColors.shirtColor = v })
watch(() => props.pantsColor, v => { currentColors.pantsColor = v })
watch(() => props.skinColor, v => { currentColors.skinColor = v })

// Curated swatches per category
const SHIRT_SWATCHES = ['C8553D', '4A7C59', '2E6B8A', '8B4513', 'B8860B', '6B2D5B', '404040', 'CC3333']
const PANTS_SWATCHES = ['2E4057', '4A3728', '3D5A3D', '2F2F2F', '5C4033', '1A3C5E', '8B7355', '555555']
const SKIN_SWATCHES = ['F4C28F', 'E8B374', 'D4A06A', 'C48E5C', 'A67853', '8B6344', '6B4E35', 'FFD5B5']

const colorItems: { key: ColorKey; label: string; swatches: string[] }[] = [
  { key: 'shirtColor', label: 'Shirt', swatches: SHIRT_SWATCHES },
  { key: 'pantsColor', label: 'Pants', swatches: PANTS_SWATCHES },
  { key: 'skinColor', label: 'Skin Tone', swatches: SKIN_SWATCHES },
]

function selectColor(key: ColorKey, value: string): void {
  currentColors[key] = value
  emit('update', key, value)
}
</script>

<style scoped>
.color-customizer__row {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}

.color-customizer__item {
  flex: 1;
  min-width: 150px;
}

.color-customizer__swatches {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.color-customizer__swatch {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  cursor: pointer;
  border: 2px solid transparent;
  transition: all 0.2s ease;
}

.color-customizer__swatch:hover {
  transform: scale(1.2);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.color-customizer__swatch--active {
  transform: scale(1.15);
  border-color: white;
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.3), 0 2px 8px rgba(0, 0, 0, 0.4);
}
</style>
