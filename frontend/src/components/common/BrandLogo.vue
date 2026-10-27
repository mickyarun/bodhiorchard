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

<!-- Product mark + wordmark. The mark swaps to its lighter tones on dark
     themes so the indigo bow stays visible against dark surfaces. -->
<template>
  <div class="brand-logo d-flex align-center">
    <img
      :src="markSrc"
      :width="size"
      :height="size"
      :alt="showText ? '' : BRAND_NAME"
    />
    <span
      v-if="showText"
      class="bo-wordmark brand-logo__name"
      :class="{ 'is-inverse': inverse }"
      :style="{ fontSize: `${textSize}px` }"
    >
      {{ BRAND_NAME }}
    </span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useTheme } from 'vuetify'
import { BRAND_MARK, BRAND_NAME } from '@/constants/brand'

const props = withDefaults(defineProps<{
  size?: number
  showText?: boolean
  // Render for a dark surface (the navy brand panel) regardless of theme.
  inverse?: boolean
}>(), {
  size: 32,
  showText: true,
  inverse: false,
})

const theme = useTheme()
const markSrc = computed(() =>
  props.inverse || theme.current.value.dark ? BRAND_MARK.dark : BRAND_MARK.light,
)
// Wordmark cap height tracks the mark so the lockup stays balanced at any size.
const textSize = computed(() => Math.round(props.size * 0.76))
</script>

<style scoped>
.brand-logo {
  gap: 10px;
}

.brand-logo__name {
  color: rgb(var(--v-theme-on-background));
  line-height: 1;
  white-space: nowrap;
}

.brand-logo__name.is-inverse {
  color: var(--color-panel-ink);
}
</style>
