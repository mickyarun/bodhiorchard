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
  <div class="char-select">
    <!-- Ambient gradient backdrop -->
    <div class="char-select__backdrop" />

    <!-- Top-left back button -->
    <v-btn
      variant="text"
      size="small"
      class="char-select__back"
      @click="router.back()"
    >
      <v-icon start>mdi-arrow-left</v-icon>
      Back
    </v-btn>

    <!-- Main two-pane stage -->
    <div class="char-select__stage">
      <!-- LEFT: 3D preview with floating HUD -->
      <section class="char-select__preview-pane">
        <CharacterPreview
          :config="previewConfig"
          class="char-select__preview"
        />

        <!-- Floating progress HUD (race-style) -->
        <div v-if="xpStore.profile" class="char-select__hud">
          <div class="char-select__hud-eyebrow">Your Progress</div>
          <div class="char-select__hud-top">
            <span class="char-select__hud-glyph">{{ levelIcon }}</span>
            <div class="char-select__hud-ident">
              <div class="char-select__hud-level">Lv.{{ xpStore.profile.level }}</div>
              <div class="char-select__hud-name">{{ levelNameDisplay }}</div>
            </div>
            <v-spacer />
            <div class="char-select__hud-xp">
              <span class="char-select__hud-xp-val">{{ xpStore.profile.total_xp.toLocaleString() }}</span>
              <span class="char-select__hud-xp-unit">XP</span>
            </div>
          </div>
          <div class="char-select__hud-bar">
            <div class="char-select__hud-bar-fill" :style="{ width: progress + '%' }" />
          </div>
          <div class="char-select__hud-meta">
            <span v-if="xpStore.profile.xp_to_next_level > 0">
              {{ xpStore.profile.xp_to_next_level.toLocaleString() }} XP to
              <strong>{{ nextLevelDisplay }}</strong>
            </span>
            <span v-else class="char-select__hud-max">Max level</span>
            <v-spacer />
            <span v-if="xpStore.profile.skill_points > 0" class="char-select__hud-sp">
              <v-icon size="12">mdi-star-four-points</v-icon>
              {{ formatSP(xpStore.profile.skill_points) }} SP
            </span>
            <span
              v-if="xpStore.profile.streak_count > 0"
              class="char-select__hud-streak"
              :class="{ 'char-select__hud-streak--hot': xpStore.profile.streak_count >= 7 }"
            >
              <v-icon size="12">{{ xpStore.profile.streak_count >= 7 ? 'mdi-fire-alert' : 'mdi-fire' }}</v-icon>
              {{ xpStore.profile.streak_count }}d
            </span>
          </div>
        </div>
      </section>

      <!-- RIGHT: Tabbed customization panel -->
      <section class="char-select__panel">
        <header class="char-select__panel-head">
          <div class="char-select__eyebrow">Character Setup</div>
          <h1 class="char-select__title">Customize Your Hero</h1>
          <p class="char-select__sub">Pick your avatar, colors, and loadout for the Bodhiorchard garden.</p>
        </header>

        <v-tabs
          v-model="tab"
          color="primary"
          density="compact"
          class="char-select__tabs"
          slider-color="primary"
          grow
        >
          <v-tab value="character">
            <v-icon start size="18">mdi-account</v-icon>Character
          </v-tab>
          <v-tab value="colors">
            <v-icon start size="18">mdi-palette</v-icon>Colors
          </v-tab>
          <v-tab value="loadout">
            <v-icon start size="18">mdi-sword-cross</v-icon>Loadout
          </v-tab>
          <v-tab value="upgrades">
            <v-icon start size="18">mdi-treasure-chest</v-icon>Upgrades
          </v-tab>
        </v-tabs>

        <v-tabs-window v-model="tab" class="char-select__panel-body">
          <v-tabs-window-item value="character">
            <CharacterGrid
              :selected-id="config.characterId"
              @select="onCharacterSelect"
            />
          </v-tabs-window-item>
          <v-tabs-window-item value="colors">
            <ColorCustomizer
              :shirt-color="config.shirtColor"
              :pants-color="config.pantsColor"
              :skin-color="config.skinColor"
              @update="onColorUpdate"
            />
          </v-tabs-window-item>
          <v-tabs-window-item value="loadout">
            <AccessoryPicker
              :right-hand="config.rightHand"
              :left-hand="config.leftHand"
              @update="onAccessoryUpdate"
            />
          </v-tabs-window-item>
          <v-tabs-window-item value="upgrades">
            <UpgradeShopPanel />
          </v-tabs-window-item>
        </v-tabs-window>
      </section>
    </div>

    <!-- Sticky bottom action bar -->
    <footer class="char-select__footer">
      <div class="char-select__footer-summary">
        <v-chip
          v-if="currentCharacterName"
          size="small"
          variant="flat"
          class="char-select__chip"
        >
          <v-icon start size="14">mdi-account</v-icon>
          {{ currentCharacterName }}
        </v-chip>
        <v-chip
          v-if="rightHandName"
          size="small"
          variant="flat"
          class="char-select__chip"
        >
          <v-icon start size="14">mdi-hand-back-right</v-icon>
          {{ rightHandName }}
        </v-chip>
        <v-chip
          v-if="leftHandName"
          size="small"
          variant="flat"
          class="char-select__chip"
        >
          <v-icon start size="14">mdi-hand-back-left</v-icon>
          {{ leftHandName }}
        </v-chip>
      </div>
      <v-btn
        color="primary"
        size="large"
        class="char-select__save"
        :loading="saving"
        :disabled="!config.characterId"
        @click="handleSave"
      >
        <v-icon start icon="mdi-check" />
        Save &amp; Continue
      </v-btn>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { reactive, computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import CharacterGrid from '@/components/character/CharacterGrid.vue'
import CharacterPreview from '@/components/character/CharacterPreview.vue'
import ColorCustomizer from '@/components/character/ColorCustomizer.vue'
import AccessoryPicker from '@/components/character/AccessoryPicker.vue'
import UpgradeShopPanel from '@/components/xp/UpgradeShopPanel.vue'
import {
  type CharacterConfig,
  parseCharacterModel,
  serializeCharacterConfig,
  DEFAULT_SHIRT_COLOR,
  DEFAULT_PANTS_COLOR,
  DEFAULT_SKIN_COLOR,
} from '@/engine/characters/CharacterConfig'
import { getCharacterDef, getAccessoryDef } from '@/engine/characters/KayKitManifest'
import { useMembersStore } from '@/stores/members'
import { useAuthStore } from '@/stores/auth'
import { useXPStore } from '@/stores/xp'
import { formatSP } from '@/utils/format'

const router = useRouter()
const membersStore = useMembersStore()
const authStore = useAuthStore()
const xpStore = useXPStore()
const saving = ref(false)
const tab = ref<'character' | 'colors' | 'loadout' | 'upgrades'>('character')

onMounted(() => { xpStore.fetchProfile() })

const existing = parseCharacterModel(authStore.user?.character_model ?? null)
const config = reactive<CharacterConfig>({
  characterId: existing.characterId,
  shirtColor: existing.shirtColor || DEFAULT_SHIRT_COLOR,
  pantsColor: existing.pantsColor || DEFAULT_PANTS_COLOR,
  skinColor: existing.skinColor || DEFAULT_SKIN_COLOR,
  rightHand: existing.rightHand || '',
  leftHand: existing.leftHand || '',
})

const previewConfig = computed<CharacterConfig>(() => ({
  characterId: config.characterId,
  shirtColor: config.shirtColor,
  pantsColor: config.pantsColor,
  skinColor: config.skinColor,
  rightHand: config.rightHand,
  leftHand: config.leftHand,
}))

const currentCharacterName = computed(() => getCharacterDef(config.characterId)?.name ?? '')
const rightHandName = computed(() => (config.rightHand ? getAccessoryDef(config.rightHand)?.name : '') ?? '')
const leftHandName = computed(() => (config.leftHand ? getAccessoryDef(config.leftHand)?.name : '') ?? '')

const LEVEL_ICONS: Record<string, string> = {
  seedling: '🌱', sprout: '🌿', sapling: '🌲', tree: '🌳', ancient_oak: '🏔️',
}
const LEVEL_NAMES = ['seedling', 'sprout', 'sapling', 'tree', 'ancient_oak']

const levelIcon = computed(() => LEVEL_ICONS[xpStore.profile?.level_name ?? ''] || '⭐')
const levelNameDisplay = computed(() => (xpStore.profile?.level_name ?? '').replace('_', ' '))
const nextLevelDisplay = computed(() => {
  const current = xpStore.profile?.level_name ?? ''
  const idx = LEVEL_NAMES.indexOf(current)
  if (idx >= 0 && idx < LEVEL_NAMES.length - 1) {
    return LEVEL_NAMES[idx + 1].replace('_', ' ')
  }
  return ''
})
const progress = computed(() => {
  const p = xpStore.profile
  if (!p || p.next_level_threshold === 0) return 100
  const into = p.next_level_threshold - p.xp_to_next_level
  return Math.min(100, (into / p.next_level_threshold) * 100)
})

function onCharacterSelect(id: string): void {
  config.characterId = id
}

function onColorUpdate(key: 'shirtColor' | 'pantsColor' | 'skinColor', value: string): void {
  config[key] = value
}

function onAccessoryUpdate(key: 'rightHand' | 'leftHand', value: string): void {
  config[key] = value
}

async function handleSave(): Promise<void> {
  if (!authStore.user) {
    await authStore.fetchUser()
  }
  const userId = authStore.user?.id
  if (!userId) {
    console.error('[CharacterSelect] No authenticated user — cannot save character')
    return
  }

  saving.value = true
  try {
    const serialized = serializeCharacterConfig(config)
    await membersStore.updateCharacter(userId, serialized)
    await authStore.fetchUser()
    router.push({ name: 'dashboard' })
  } catch (err) {
    console.error('[CharacterSelect] Failed to save:', err)
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.char-select {
  position: relative;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  color: #fff;
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
  isolation: isolate;
}

.char-select__backdrop {
  position: fixed;
  inset: 0;
  z-index: -1;
  background:
    radial-gradient(ellipse 80% 60% at 70% 20%, rgba(46, 125, 50, 0.18), transparent 60%),
    radial-gradient(ellipse 60% 80% at 10% 90%, rgba(22, 48, 30, 0.35), transparent 60%),
    linear-gradient(180deg, #0a130f 0%, #060c08 100%);
}

/* ── Back button ────────────────────────────── */
.char-select__back {
  position: absolute;
  top: 16px;
  left: 16px;
  z-index: 5;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-size: 11px !important;
}

/* ── Stage ──────────────────────────────────── */
.char-select__stage {
  flex: 1;
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
  align-items: start;
  gap: 24px;
  padding: 56px 28px 108px;
  max-width: 1600px;
  width: 100%;
  margin: 0 auto;
}

@media (max-width: 960px) {
  .char-select__stage {
    grid-template-columns: 1fr;
    padding: 52px 16px 120px;
    gap: 16px;
  }
}

/* ── Preview pane ───────────────────────────── */
.char-select__preview-pane {
  position: sticky;
  top: 20px;
  height: calc(100vh - 180px);
  min-height: 520px;
  border-radius: 20px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.02), rgba(0, 0, 0, 0.2));
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.35);
}

@media (max-width: 960px) {
  .char-select__preview-pane {
    position: relative;
    top: auto;
    height: 380px;
    min-height: 380px;
  }
}

.char-select__preview {
  height: 100%;
  border-radius: 0 !important;
}

/* ── Floating HUD ───────────────────────────── */
.char-select__hud {
  position: absolute;
  top: 18px;
  left: 18px;
  right: 18px;
  max-width: 420px;
  padding: 14px 18px 12px;
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(10, 22, 14, 0.82), rgba(10, 22, 14, 0.7));
  border: 1px solid rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(8px);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.3);
  pointer-events: none;
}

.char-select__hud-eyebrow {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.55);
  margin-bottom: 8px;
}

.char-select__hud-top {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.char-select__hud-glyph {
  font-size: 22px;
  line-height: 1;
}

.char-select__hud-ident {
  display: flex;
  flex-direction: column;
  line-height: 1.1;
}

.char-select__hud-level {
  font-size: 15px;
  font-weight: 800;
  letter-spacing: -0.01em;
}

.char-select__hud-name {
  font-size: 11px;
  text-transform: capitalize;
  color: rgba(255, 255, 255, 0.6);
}

.char-select__hud-xp {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.char-select__hud-xp-val {
  font-size: 22px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  color: rgb(var(--v-theme-secondary));
  letter-spacing: -0.02em;
}

.char-select__hud-xp-unit {
  font-size: 11px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.5);
  letter-spacing: 0.08em;
}

.char-select__hud-bar {
  height: 6px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
  margin-bottom: 8px;
}

.char-select__hud-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, rgb(var(--v-theme-primary)), rgb(var(--v-theme-secondary)));
  transition: width 0.6s ease;
}

.char-select__hud-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.65);
}

.char-select__hud-meta strong {
  color: rgb(var(--v-theme-secondary));
  font-weight: 700;
  text-transform: capitalize;
}

.char-select__hud-max {
  color: rgb(var(--v-theme-secondary));
  font-weight: 700;
}

.char-select__hud-sp,
.char-select__hud-streak {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  padding: 2px 7px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  font-size: 10px;
}

.char-select__hud-streak--hot {
  background: rgba(255, 87, 34, 0.18);
  color: #ffb199;
  animation: pulse-flame 1.5s ease-in-out infinite;
}

@keyframes pulse-flame {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.06); }
}

/* ── Panel ──────────────────────────────────── */
.char-select__panel {
  display: flex;
  flex-direction: column;
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: linear-gradient(180deg, rgba(15, 28, 20, 0.85) 0%, rgba(8, 16, 12, 0.9) 100%);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.35);
  overflow: hidden;
}

.char-select__panel-head {
  padding: 22px 24px 8px;
}

.char-select__eyebrow {
  display: inline-block;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.55);
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  margin-bottom: 10px;
}

.char-select__title {
  font-size: 26px;
  font-weight: 900;
  letter-spacing: -0.02em;
  font-style: italic;
  margin: 0 0 4px;
}

.char-select__sub {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.55);
  margin: 0;
}

.char-select__tabs {
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  min-height: 48px;
}

.char-select__tabs :deep(.v-tab) {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  min-height: 48px;
}

.char-select__panel-body {
  padding: 20px 24px 24px;
}

/* Let v-window collapse to the active tab's height — prevents a tall empty
   area when switching from a long tab (Character/Upgrades) to a short one
   (Colors). */
.char-select__panel-body :deep(.v-window__container) {
  height: auto !important;
}

.char-select__panel-body :deep(.v-window-item--active) {
  height: auto;
}

/* ── Sticky footer ──────────────────────────── */
.char-select__footer {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 4;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 28px;
  background: linear-gradient(180deg, rgba(6, 12, 8, 0.75), rgba(6, 12, 8, 0.95));
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(10px);
}

.char-select__footer-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

.char-select__chip {
  background: rgba(255, 255, 255, 0.06) !important;
  border: 1px solid rgba(255, 255, 255, 0.08) !important;
  font-weight: 600;
}

.char-select__save {
  font-weight: 800 !important;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  min-width: 200px;
}

@media (max-width: 600px) {
  .char-select__footer {
    padding: 12px 14px;
    flex-direction: column;
    align-items: stretch;
  }
  .char-select__save {
    width: 100%;
  }
}
</style>
