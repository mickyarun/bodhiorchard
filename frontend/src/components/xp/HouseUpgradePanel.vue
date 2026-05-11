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
  <div>
    <div class="d-flex align-center mb-4">
      <v-icon size="20" class="mr-2" color="secondary">mdi-home-group</v-icon>
      <span class="text-subtitle-2 font-weight-bold text-uppercase" style="letter-spacing: 0.05em;">
        House
      </span>
      <v-spacer />
      <v-chip size="x-small" variant="tonal" color="secondary">
        Tier {{ currentTier }}
      </v-chip>
    </div>

    <!-- Current tier display -->
    <div class="d-flex align-center pa-3 rounded-lg mb-3" style="border: 1px solid rgba(var(--v-theme-success), 0.2); background: rgba(var(--v-theme-success), 0.04);">
      <div
        class="d-flex align-center justify-center rounded-lg mr-3 bg-success"
        style="width: 40px; height: 40px;"
      >
        <v-icon color="white" size="22">{{ currentTierIcon }}</v-icon>
      </div>
      <div>
        <div class="text-body-2 font-weight-medium">{{ currentTierName }}</div>
        <div class="text-caption text-medium-emphasis">Current home</div>
      </div>
    </div>

    <!-- Upgrade option -->
    <div
      v-if="nextTier"
      class="d-flex align-center pa-3 rounded-lg"
      style="border: 1px dashed rgba(var(--v-theme-primary), 0.3); background: rgba(var(--v-theme-primary), 0.04);"
    >
      <div
        class="d-flex align-center justify-center rounded-lg mr-3 bg-surface-variant"
        style="width: 40px; height: 40px;"
      >
        <v-icon color="medium-emphasis" size="22">{{ nextTier.icon }}</v-icon>
      </div>
      <div class="flex-grow-1">
        <div class="text-body-2 font-weight-medium">{{ nextTier.name }}</div>
        <div class="text-caption text-medium-emphasis">{{ nextTier.cost }} skill points</div>
      </div>
      <v-btn
        size="small"
        variant="flat"
        color="primary"
        :loading="upgrading"
        :disabled="skillPoints < nextTier.cost"
        @click="upgrade"
      >
        <v-icon start size="16">mdi-arrow-up-bold</v-icon>
        Upgrade
      </v-btn>
    </div>
    <div
      v-else
      class="text-caption text-medium-emphasis text-center pa-2"
    >
      Maximum tier reached
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import api from '@/services/api'
import { useXPStore } from '@/stores/xp'

const xpStore = useXPStore()
const upgrading = ref(false)

const tiers = [
  { tier: 1, name: 'Hut', cost: 0, icon: 'mdi-home-outline' },
  { tier: 2, name: 'Cottage', cost: 50, icon: 'mdi-home' },
  { tier: 3, name: 'Mansion', cost: 100, icon: 'mdi-home-city' },
]

const currentTier = computed(() => xpStore.profile?.house_level ?? 1)
const currentTierData = computed(() => tiers.find(t => t.tier === currentTier.value))
const currentTierName = computed(() => currentTierData.value?.name ?? 'Hut')
const currentTierIcon = computed(() => currentTierData.value?.icon ?? 'mdi-home-outline')
const skillPoints = computed(() => xpStore.profile?.skill_points ?? 0)

const nextTier = computed(() => tiers.find(t => t.tier === currentTier.value + 1) ?? null)

async function upgrade(): Promise<void> {
  if (!nextTier.value) return
  upgrading.value = true
  try {
    await api.post('/v1/xp/upgrade-house', { target_tier: nextTier.value.tier })
    await xpStore.fetchProfile()
  } catch (err) {
    console.error('[HouseUpgradePanel] upgrade failed:', err)
  } finally {
    upgrading.value = false
  }
}
</script>
