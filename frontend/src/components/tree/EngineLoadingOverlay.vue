<!-- SPDX-License-Identifier: AGPL-3.0-or-later
     Copyright (C) 2026 Arun Rajkumar -->
<template>
  <Transition name="fade">
    <div
      v-if="visible"
      class="engine-loader"
      role="status"
      aria-live="polite"
      aria-busy="true"
      :aria-label="`Loading orchard — ${currentPhaseLabel}`"
    >
      <!-- Layered organic backdrop. Two radial glows + animated noise so the
           overlay reads as 'a world being summoned' rather than 'an empty
           splash screen with a spinner stuck in the middle.' -->
      <div class="engine-loader__backdrop" />
      <div class="engine-loader__sky" />
      <div class="engine-loader__horizon" />

      <div class="engine-loader__content">
        <!-- Animated bodhi-tree silhouette. SVG rather than canvas so it
             stays smooth at any density and doesn't compete with the
             PlayCanvas device for GPU during init. -->
        <svg
          class="engine-loader__tree"
          viewBox="0 0 200 220"
          aria-hidden="true"
        >
          <defs>
            <radialGradient id="canopyGlow" cx="50%" cy="40%" r="55%">
              <stop offset="0%" stop-color="#a8e6a3" stop-opacity="0.95" />
              <stop offset="60%" stop-color="#5fb35a" stop-opacity="0.7" />
              <stop offset="100%" stop-color="#2f6d2c" stop-opacity="0.0" />
            </radialGradient>
            <linearGradient id="trunkGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="#7a5436" />
              <stop offset="100%" stop-color="#4a311e" />
            </linearGradient>
          </defs>

          <!-- Glow halo — pulses with progress -->
          <circle
            class="engine-loader__halo"
            cx="100" cy="90" r="70"
            fill="url(#canopyGlow)"
          />

          <!-- Trunk: simple tapered shape -->
          <path
            class="engine-loader__trunk"
            d="M 92 200 L 95 130 L 105 130 L 108 200 Z"
            fill="url(#trunkGrad)"
          />

          <!-- Canopy: 5 leaf clusters that 'grow' in sequence -->
          <g class="engine-loader__canopy">
            <circle class="engine-loader__leaf engine-loader__leaf--1" cx="100" cy="80"  r="38" />
            <circle class="engine-loader__leaf engine-loader__leaf--2" cx="68"  cy="105" r="26" />
            <circle class="engine-loader__leaf engine-loader__leaf--3" cx="132" cy="105" r="26" />
            <circle class="engine-loader__leaf engine-loader__leaf--4" cx="80"  cy="60"  r="22" />
            <circle class="engine-loader__leaf engine-loader__leaf--5" cx="120" cy="60"  r="22" />
          </g>

          <!-- Drifting glyph particles to suggest 'data flowing into the world' -->
          <g class="engine-loader__particles" aria-hidden="true">
            <circle class="engine-loader__particle engine-loader__particle--a" cx="40"  cy="160" r="2" />
            <circle class="engine-loader__particle engine-loader__particle--b" cx="160" cy="150" r="2" />
            <circle class="engine-loader__particle engine-loader__particle--c" cx="100" cy="180" r="2" />
            <circle class="engine-loader__particle engine-loader__particle--d" cx="60"  cy="190" r="2" />
            <circle class="engine-loader__particle engine-loader__particle--e" cx="140" cy="190" r="2" />
          </g>
        </svg>

        <h1 class="engine-loader__brand">bodhiorchard</h1>
        <p class="engine-loader__phase">{{ currentPhaseLabel }}</p>

        <!-- Progress bar. Fills smoothly as phase advances. -->
        <div
          class="engine-loader__bar"
          :aria-valuenow="progressPct"
          aria-valuemin="0"
          aria-valuemax="100"
          role="progressbar"
        >
          <div
            class="engine-loader__bar-fill"
            :style="{ width: progressPct + '%' }"
          />
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed } from 'vue'

/**
 * Engine loading overlay. Sits on top of the PlayCanvas canvas while the
 * engine boots and the scene assembles, so the user never sees the bare
 * black canvas, the partial scene popping into existence, or the
 * first-render flicker.
 *
 * `phase` advances through ordered states; the bar fills proportionally
 * and the parent fades the overlay out by toggling `visible`.
 */
export type LoadingPhase =
  | 'mounting'         // Vue mounted, waiting for init() to start
  | 'engine_init'      // pc.Application created, lighting set up, scatter assets loaded
  | 'building_scene'   // SceneManager.build() running — assembling the world
  | 'connecting'       // joining OrgRoom + fetching profile
  | 'ready'            // scene reveal — caller flips visible=false here

const props = defineProps<{
  visible: boolean
  phase: LoadingPhase
}>()

// Phase progress weighting: 'building_scene' is the longest by far on prod
// hardware (5–15s with 100+ GLBs), so it gets the bulk of the bar. Values
// chosen so the bar appears to advance steadily rather than jumping at the
// transition between fast and slow phases.
const PHASE_PROGRESS: Record<LoadingPhase, number> = {
  mounting:        5,
  engine_init:    25,
  building_scene: 80,
  connecting:     95,
  ready:         100,
}

const PHASE_LABELS: Record<LoadingPhase, string> = {
  mounting:        'Preparing the orchard…',
  engine_init:     'Gathering trees & seeds…',
  building_scene:  'Planting the orchard…',
  connecting:      'Calling the others…',
  ready:           'Welcome.',
}

const currentPhaseLabel = computed(() => PHASE_LABELS[props.phase])
const progressPct = computed(() => PHASE_PROGRESS[props.phase])
</script>

<style scoped>
.engine-loader {
  position: absolute;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  /* Hide the bare canvas behind us during boot */
  background: #1a2f1a;
  /* Subpixel rendering hint — prevents the SVG halo from showing
     hairline seams during the scale animation. */
  backface-visibility: hidden;
  user-select: none;
}

/* ─── Layered backdrop ──────────────────────────────────────────────── */
.engine-loader__backdrop {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse 80% 60% at 50% 70%, #2f5a32 0%, #0e1f10 70%),
    linear-gradient(180deg, #0b1e20 0%, #1a3128 100%);
}

.engine-loader__sky {
  position: absolute;
  inset: 0;
  background: radial-gradient(
    ellipse 70% 50% at 50% 0%,
    rgba(240, 200, 130, 0.35) 0%,
    transparent 60%
  );
  /* Subtle warm glow from the top — golden-hour feel matching the engine */
  animation: skyPulse 6s ease-in-out infinite;
}

.engine-loader__horizon {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 38%;
  background: linear-gradient(
    180deg,
    transparent 0%,
    rgba(15, 35, 18, 0.6) 60%,
    rgba(8, 20, 10, 0.95) 100%
  );
}

@keyframes skyPulse {
  0%, 100% { opacity: 0.85; }
  50%      { opacity: 1; }
}

/* ─── Content stack ─────────────────────────────────────────────────── */
.engine-loader__content {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 18px;
  padding: 32px;
  max-width: 380px;
  text-align: center;
}

.engine-loader__tree {
  width: 180px;
  height: 200px;
  filter: drop-shadow(0 12px 24px rgba(0, 0, 0, 0.5));
}

/* ─── Tree growth animation ─────────────────────────────────────────── */
.engine-loader__halo {
  transform-origin: 100px 90px;
  animation: haloPulse 3.2s ease-in-out infinite;
}

@keyframes haloPulse {
  0%, 100% { transform: scale(0.95); opacity: 0.8; }
  50%      { transform: scale(1.05); opacity: 1.0; }
}

.engine-loader__trunk {
  transform-origin: 100px 200px;
  animation: trunkGrow 1.4s ease-out 0.1s both;
}

@keyframes trunkGrow {
  from { transform: scaleY(0); }
  to   { transform: scaleY(1); }
}

.engine-loader__leaf {
  fill: #4f9c4a;
  transform-origin: center;
  opacity: 0;
  animation: leafGrow 1.0s ease-out both;
}
.engine-loader__leaf--1 { animation-delay: 1.0s; fill: #62b85c; }
.engine-loader__leaf--2 { animation-delay: 1.3s; }
.engine-loader__leaf--3 { animation-delay: 1.5s; }
.engine-loader__leaf--4 { animation-delay: 1.7s; fill: #74c66f; }
.engine-loader__leaf--5 { animation-delay: 1.9s; fill: #74c66f; }

@keyframes leafGrow {
  0%   { transform: scale(0);   opacity: 0; }
  60%  { transform: scale(1.1); opacity: 1; }
  100% { transform: scale(1);   opacity: 0.95; }
}

/* ─── Drifting particles ────────────────────────────────────────────── */
.engine-loader__particle {
  fill: #c9eac4;
  opacity: 0;
  animation: particleDrift 4.5s ease-in-out infinite;
}
.engine-loader__particle--a { animation-delay: 0.0s; }
.engine-loader__particle--b { animation-delay: 0.9s; }
.engine-loader__particle--c { animation-delay: 1.5s; }
.engine-loader__particle--d { animation-delay: 2.2s; }
.engine-loader__particle--e { animation-delay: 3.0s; }

@keyframes particleDrift {
  0%   { transform: translate(0, 0)    scale(0.8); opacity: 0; }
  20%  {                                            opacity: 0.9; }
  100% { transform: translate(0, -60px) scale(1.2); opacity: 0; }
}

/* ─── Brand + label ─────────────────────────────────────────────────── */
.engine-loader__brand {
  margin: 0;
  font-family: 'Inter', system-ui, sans-serif;
  font-size: 22px;
  font-weight: 600;
  letter-spacing: 0.18em;
  color: #f4e8c8;
  text-transform: lowercase;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.6);
}

.engine-loader__phase {
  margin: 0;
  font-family: 'Inter', system-ui, sans-serif;
  font-size: 13px;
  font-weight: 400;
  color: rgba(244, 232, 200, 0.78);
  letter-spacing: 0.04em;
  min-height: 1.4em; /* prevents reflow on label change */
}

/* ─── Progress bar ──────────────────────────────────────────────────── */
.engine-loader__bar {
  width: 240px;
  height: 4px;
  background: rgba(255, 255, 255, 0.10);
  border-radius: 999px;
  overflow: hidden;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.06);
}

.engine-loader__bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #a8e6a3 0%, #ffd964 100%);
  border-radius: 999px;
  transition: width 600ms cubic-bezier(0.22, 1, 0.36, 1);
  box-shadow: 0 0 12px rgba(168, 230, 163, 0.6);
}

/* ─── Reveal transition ─────────────────────────────────────────────── */
/* Fade the overlay out over ~600ms so the scene doesn't suddenly snap
   in — gives the brain a moment to register 'we've arrived.' */
.fade-leave-active {
  transition: opacity 600ms cubic-bezier(0.22, 1, 0.36, 1);
}
.fade-leave-to {
  opacity: 0;
}

/* Reduced-motion accessibility: keep the layout, drop the animations. */
@media (prefers-reduced-motion: reduce) {
  .engine-loader__halo,
  .engine-loader__sky,
  .engine-loader__particle,
  .engine-loader__leaf,
  .engine-loader__trunk {
    animation: none;
    opacity: 1;
    transform: none;
  }
}
</style>
