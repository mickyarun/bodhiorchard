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
     for the current session only. Visual rhythm: gold left-rule as the
     structural anchor (race-chrome continuity), hanging italic title
     with an accent period, verb-led key rows, a literal drain demo
     instead of an abstract 3-zone band, asymmetric action row. -->
<template>
  <v-dialog v-model="open" max-width="480">
    <v-card class="stamina-intro">
      <header class="stamina-intro__head">
        <span class="stamina-intro__tag">
          <CheckerFlagIcon :size="11" />
          Race brief · 01
        </span>
        <h2 class="stamina-intro__title">
          Pace your<br>stamina<span class="stamina-intro__dot">.</span>
        </h2>
      </header>

      <ol class="stamina-intro__binds">
        <li>
          <span class="stamina-intro__verb">Hold</span>
          <span class="stamina-intro__keys">
            <kbd>W</kbd><span class="stamina-intro__or">or</span><kbd>↑</kbd>
          </span>
          <span class="stamina-intro__outcome">to run</span>
        </li>
        <li>
          <span class="stamina-intro__verb">Tap</span>
          <span class="stamina-intro__keys"><kbd>Shift</kbd></span>
          <span class="stamina-intro__outcome">to sprint</span>
        </li>
      </ol>

      <figure class="stamina-intro__meter" aria-label="Stamina meter sample">
        <div class="stamina-intro__bar">
          <div class="stamina-intro__bar-fill" />
        </div>
        <figcaption class="stamina-intro__legend">
          <span class="stamina-intro__legend-full">Full</span>
          <span class="stamina-intro__legend-empty">Empty</span>
        </figcaption>
      </figure>

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

      <footer class="stamina-intro__actions">
        <button type="button" class="stamina-intro__skip" @click="dismissOnce">
          Skip for now
        </button>
        <button type="button" class="cta__pill cta__pill--host" @click="dismissForever">
          <v-icon icon="mdi-check" size="14" />
          Got it
        </button>
      </footer>
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
/* The dark backdrop is pinned here so the dialog reads correctly under
   the forest design system's auto light/dark theme — race surfaces are
   deliberately cinematic-dark everywhere, matching .race-room-view.
   3px gold left rule is the single asymmetric anchor; the eye lands
   there before reading the title. */
.stamina-intro.v-card {
  background: linear-gradient(180deg, #0f1726 0%, #0a0f1a 100%);
  color: #fff;
  border: 1px solid rgba(255, 215, 94, 0.18);
  border-left: 3px solid rgba(255, 215, 94, 0.65);
  border-radius: 14px;
  padding: 26px 28px 22px;
}

.stamina-intro__head {
  margin-bottom: 22px;
}
.stamina-intro__tag {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  text-transform: uppercase;
  letter-spacing: 0.22em;
  font-size: 10px;
  font-weight: 700;
  color: rgba(255, 215, 94, 0.85);
  margin-bottom: 12px;
}
.stamina-intro__title {
  font-size: clamp(28px, 4vw, 36px);
  font-weight: 900;
  font-style: italic;
  letter-spacing: -0.025em;
  line-height: 0.98;
  margin: 0;
}
/* Gold period as a tiny accent — mirrors the left rule. */
.stamina-intro__dot {
  color: rgba(255, 215, 94, 0.95);
}

/* Verb-led mini-table: HOLD · [W][↑] · to run. Reads in the order the
   player will use the keys, not in default visual hierarchy. */
.stamina-intro__binds {
  list-style: none;
  margin: 0 0 18px;
  padding: 14px 0;
  display: grid;
  gap: 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.07);
  border-bottom: 1px solid rgba(255, 255, 255, 0.07);
}
.stamina-intro__binds li {
  display: grid;
  grid-template-columns: 48px auto 1fr;
  align-items: center;
  gap: 14px;
}
.stamina-intro__verb {
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-size: 10px;
  font-weight: 800;
  color: rgba(255, 215, 94, 0.8);
}
.stamina-intro__keys {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.stamina-intro__or {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.45);
}
.stamina-intro__keys kbd {
  padding: 3px 9px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-bottom-color: rgba(255, 255, 255, 0.3);
  border-radius: 5px;
  font-family: inherit;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  min-width: 24px;
  text-align: center;
}
.stamina-intro__outcome {
  font-style: italic;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.6);
}

/* Literal drain visualization — full on the left, empty on the right,
   fill at 65% to show what a mid-race stamina state actually looks
   like. Matches the live HUD's RacerStaminaBar palette so seeing this
   here primes the player to recognise it in-race. */
.stamina-intro__meter {
  margin: 0 0 18px;
}
.stamina-intro__bar {
  position: relative;
  height: 8px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
  margin-bottom: 6px;
}
.stamina-intro__bar-fill {
  height: 100%;
  width: 65%;
  background: linear-gradient(90deg, rgb(80, 200, 120) 0%, rgb(240, 196, 76) 100%);
}
.stamina-intro__legend {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-weight: 700;
}
.stamina-intro__legend-full { color: rgba(80, 200, 120, 0.9); }
.stamina-intro__legend-empty { color: rgba(232, 96, 88, 0.9); }

/* AppCallout colours its body with `--v-theme-on-surface`, which tracks
   the active forest theme. This card is pinned dark regardless of theme,
   so under light mode that token resolves near-black and the body reads
   invisible dark-on-dark. Pin the callout surface, border, and text to
   the same dark palette the card uses; the gold eyebrow already uses the
   theme-independent warning token, so it's left alone. */
.stamina-intro__callout {
  margin-bottom: 20px;
  border-color: rgba(255, 215, 94, 0.16);
  background: rgba(255, 215, 94, 0.06);
}
.stamina-intro__callout :deep(.app-callout__text) {
  color: rgba(255, 255, 255, 0.78);
}
.stamina-intro__callout :deep(.app-callout__icon) {
  background: rgba(255, 215, 94, 0.14);
}

/* Asymmetric action row: ghost is a quiet text link, gold pill is the
   visual anchor. The eye reads "skip for now … GOT IT" as a sentence,
   not a binary choice between equals. */
.stamina-intro__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.stamina-intro__skip {
  background: transparent;
  border: none;
  padding: 8px 0;
  font-family: inherit;
  font-size: 12px;
  letter-spacing: 0.04em;
  color: rgba(255, 255, 255, 0.55);
  cursor: pointer;
  text-decoration: underline;
  text-decoration-color: rgba(255, 255, 255, 0.2);
  text-underline-offset: 4px;
  transition: color 0.15s, text-decoration-color 0.15s;
}
.stamina-intro__skip:hover {
  color: rgba(255, 255, 255, 0.85);
  text-decoration-color: rgba(255, 215, 94, 0.5);
}
.stamina-intro__skip:focus-visible {
  outline: 2px solid rgba(255, 215, 94, 0.7);
  outline-offset: 4px;
  border-radius: 3px;
}
</style>
