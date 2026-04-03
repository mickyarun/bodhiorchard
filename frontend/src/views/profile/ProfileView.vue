<template>
  <v-container class="py-6" fluid>
    <div class="d-flex align-center mb-6">
      <v-icon icon="mdi-account-circle" size="28" class="mr-2" />
      <div class="text-h5 font-weight-bold">My Profile</div>
      <v-spacer />
      <v-btn
        variant="tonal"
        color="primary"
        prepend-icon="mdi-account-edit-outline"
        to="/character-select"
      >
        Customize Character
      </v-btn>
    </div>

    <!-- XP Profile Card -->
    <XPProfileCard
      v-if="xpStore.profile"
      :total-xp="xpStore.profile.total_xp"
      :level="xpStore.profile.level"
      :level-name="xpStore.profile.level_name"
      :xp-to-next-level="xpStore.profile.xp_to_next_level"
      :next-level-threshold="xpStore.profile.next_level_threshold"
      :streak-count="xpStore.profile.streak_count"
      class="mb-6"
    />

    <v-row>
      <!-- Left: XP History -->
      <v-col cols="12" md="7">
        <XPHistoryFeed />
      </v-col>

      <!-- Right: How to Earn + Character Preview -->
      <v-col cols="12" md="5">
        <XPInfoPanel class="mb-4" />

        <!-- Character preview -->
        <v-card color="surface" class="profile__preview-card">
          <CharacterPreview
            v-if="characterConfig"
            :config="characterConfig"
            class="profile__preview"
          />
          <div v-else class="d-flex align-center justify-center h-100 text-medium-emphasis">
            <v-icon icon="mdi-account-outline" size="48" />
          </div>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useXPStore } from '@/stores/xp'
import { useAuthStore } from '@/stores/auth'
import { parseCharacterModel, isKayKitConfig, type CharacterConfig } from '@/engine/characters/CharacterConfig'
import XPProfileCard from '@/components/xp/XPProfileCard.vue'
import XPHistoryFeed from '@/components/xp/XPHistoryFeed.vue'
import XPInfoPanel from '@/components/xp/XPInfoPanel.vue'
import CharacterPreview from '@/components/character/CharacterPreview.vue'

const xpStore = useXPStore()
const authStore = useAuthStore()

const characterConfig = computed<CharacterConfig | null>(() => {
  const model = authStore.user?.character_model
  if (!model) return null
  const config = parseCharacterModel(model)
  return isKayKitConfig(config) ? config : null
})

onMounted(() => {
  xpStore.fetchProfile()
})
</script>

<style scoped>
.profile__preview-card {
  height: 300px;
  overflow: hidden;
}
.profile__preview {
  height: 100%;
}
</style>
