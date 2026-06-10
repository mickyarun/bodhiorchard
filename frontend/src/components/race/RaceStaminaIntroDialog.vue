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

<!-- One-shot onboarding popup for the stamina mechanic. Surfaces in the
     lobby (when there's time to read) the first time a player joins a
     race; "Got it" stores the dismissal in localStorage. Skip closes
     for the current session only. Visual rhythm matches the rest of the
     race chrome: eyebrow → italic title → AppCallout body → pill row. -->
<template>
  <v-dialog v-model="open" max-width="500">
    <v-card class="stamina-intro" color="surface">
      <div class="stamina-intro__eyebrow">
        <CheckerFlagIcon :size="12" />
        Race brief
      </div>
      <h2 class="stamina-intro__title">Pace your stamina</h2>

      <div class="stamina-intro__keys">
        <div class="stamina-intro__key-row">
          <v-icon icon="mdi-arrow-right-bold-outline" size="18" />
          <span class="stamina-intro__key-label">Hold to move</span>
          <span class="stamina-intro__key-binding"><kbd>W</kbd> or <kbd>↑</kbd></span>
        </div>
        <div class="stamina-intro__key-row">
          <v-icon icon="mdi-flash-outline" size="18" />
          <span class="stamina-intro__key-label">Tap to sprint</span>
          <span class="stamina-intro__key-binding"><kbd>Shift</kbd></span>
        </div>
      </div>

      <div class="stamina-intro__bar-demo">
        <div class="stamina-intro__bar-track">
          <div class="stamina-intro__bar-fill" />
        </div>
        <div class="stamina-intro__bar-zones">
          <span class="stamina-intro__zone stamina-intro__zone--ok">Safe to sprint</span>
          <span class="stamina-intro__zone stamina-intro__zone--warn">Pace yourself</span>
          <span class="stamina-intro__zone stamina-intro__zone--low">Rest now</span>
        </div>
      </div>

      <AppCallout
        variant="warning"
        eyebrow="The trade-off"
        icon="mdi-lightning-bolt-outline"
        class="stamina-intro__callout"
      >
        Sprint drains stamina; walking refills it. Two or three well-timed
        bursts beat tapping forever — gas out and you'll drop to a walk
        for the rest of the race.
      </AppCallout>

      <div class="stamina-intro__actions">
        <button type="button" class="cta__pill cta__pill--ghost" @click="dismissOnce">
          Skip
        </button>
        <button type="button" class="cta__pill cta__pill--host" @click="dismissForever">
          <v-icon icon="mdi-check" size="16" />
          Got it
        </button>
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import CheckerFlagIcon from '@/components/race/CheckerFlagIcon.vue'

// localStorage flag — once "Got it" is clicked, every future race
// auto-dismisses. Naming follows the existing bodhiorchard_<feature>
// key convention (see AppLayout's sidebar-rail key).
const SEEN_KEY = 'bodhiorchard_race_stamina_intro_seen'

const props = defineProps<{
  // True while the player is in the lobby of a race they're a
  // participant in. Parent owns the gating so the dialog stays focused
  // on its own concerns (read storage, render, dismiss).
  active: boolean
}>()

const open = ref(false)

watch(
  () => props.active,
  (active) => {
    if (!active) {
      open.value = false
      return
    }
    if (localStorage.getItem(SEEN_KEY) === 'true') return
    open.value = true
  },
  { immediate: true },
)

function dismissOnce(): void {
  open.value = false
}

function dismissForever(): void {
  localStorage.setItem(SEEN_KEY, 'true')
  open.value = false
}
</script>

<style scoped>
.stamina-intro {
  padding: 26px 26px 22px;
  border-radius: 14px;
}
.stamina-intro__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  text-transform: uppercase;
  letter-spacing: 0.2em;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.6);
  font-weight: 600;
  padding: 5px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  margin-bottom: 14px;
}
.stamina-intro__title {
  font-size: clamp(22px, 3vw, 28px);
  font-weight: 900;
  font-style: italic;
  letter-spacing: -0.02em;
  line-height: 1.1;
  margin: 0 0 18px;
}

/* Key-binding rows. Tiny mini-table so the input vocabulary is visible
   before the player reads the prose explanation. */
.stamina-intro__keys {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 18px;
}
.stamina-intro__key-row {
  display: grid;
  grid-template-columns: 24px 1fr auto;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.85);
}
.stamina-intro__key-label {
  font-weight: 500;
}
.stamina-intro__key-binding {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.65);
}
.stamina-intro__key-binding kbd {
  padding: 2px 8px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 6px;
  font-family: inherit;
  font-size: 11px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.85);
}

/* Visual demo of the stamina bar — same green/amber/red palette as the
   live HUD's RacerStaminaBar so what they see here matches in-race. */
.stamina-intro__bar-demo {
  margin-bottom: 18px;
}
.stamina-intro__bar-track {
  position: relative;
  height: 8px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
  margin-bottom: 8px;
}
.stamina-intro__bar-fill {
  height: 100%;
  width: 100%;
  background: linear-gradient(
    90deg,
    rgb(232, 96, 88) 0%,
    rgb(232, 96, 88) 25%,
    rgb(240, 196, 76) 25%,
    rgb(240, 196, 76) 60%,
    rgb(80, 200, 120) 60%,
    rgb(80, 200, 120) 100%
  );
}
.stamina-intro__bar-zones {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}
.stamina-intro__zone--ok {
  color: rgb(80, 200, 120);
}
.stamina-intro__zone--warn {
  color: rgb(240, 196, 76);
}
.stamina-intro__zone--low {
  color: rgb(232, 96, 88);
}

.stamina-intro__callout {
  margin-bottom: 18px;
}

.stamina-intro__actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}
</style>
