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

<!-- One-click light/dark switch for the sidebar footer. The icon shows the
     theme it switches to. "Follow the system" stays in the account menu. -->
<template>
  <v-btn
    :icon="isDark ? 'mdi-white-balance-sunny' : 'mdi-weather-night'"
    variant="text"
    :size="size"
    density="comfortable"
    :aria-label="label"
    :title="label"
    @click="toggle"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useThemePreference } from '@/composables/useThemePreference'

// Phones get the default size: a comfortable touch target.
withDefaults(defineProps<{ size?: 'small' | 'default' }>(), { size: 'small' })

const { isDark, toggle } = useThemePreference()
const label = computed(() => (isDark.value ? 'Switch to light theme' : 'Switch to dark theme'))
</script>
