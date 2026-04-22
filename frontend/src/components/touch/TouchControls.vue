<!--
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2026 Arun Rajkumar

  TouchControls — root overlay for on-screen controls in the 3D view.

  Layout:
    ┌────────────────────────────────────────┐
    │                               [Esc]    │
    │                                        │
    │                               [V][E]   │
    │                                  [⤒]   │  Space / jump
    │                                        │
    │   (open area: swipe to orbit)          │
    │                                        │
    │     ○ joystick                [Shift]  │
    │              [1][2][3][4]              │
    └────────────────────────────────────────┘

  The wrapper has pointer-events: none so touches in empty areas fall
  through to the PlayCanvas canvas (camera orbit). Each widget sets
  pointer-events: auto to capture its own touches.

  Context-specific button sets keep each mode focused:
    - garden-takeover: full set
    - race: joystick + Shift (sprint) + Space (jump only)
    - interior: joystick + E (interact) + Esc
-->

<template>
  <div class="touch-controls" :class="`touch-controls--${context}`">
    <TouchJoystick />

    <!-- Right-side action stack -->
    <div class="touch-controls__right">
      <TouchButton
        v-if="showEscape"
        label="Esc"
        code="Escape"
        mode="tap"
        variant="exit"
        aria-label="Exit"
        class="touch-controls__exit"
      />
      <TouchButton
        v-if="showMount"
        label="V"
        code="KeyV"
        mode="tap"
        variant="primary"
        aria-label="Mount or dismount"
      />
      <TouchButton
        v-if="showInteract"
        label="E"
        code="KeyE"
        mode="tap"
        variant="primary"
        aria-label="Interact or sit"
      />
      <TouchButton
        v-if="showJump"
        label="⤒"
        code="Space"
        mode="tap"
        variant="primary"
        aria-label="Jump"
      />
      <TouchButton
        v-if="showSprint"
        label="Shift"
        code="ShiftLeft"
        mode="hold"
        variant="primary"
        aria-label="Sprint"
      />
    </div>

    <!-- Bottom-centre emote row (takeover only) -->
    <div v-if="showEmotes" class="touch-controls__emotes">
      <TouchButton label="1" code="Digit1" mode="tap" variant="emote" aria-label="Wave" />
      <TouchButton label="2" code="Digit2" mode="tap" variant="emote" aria-label="Cheer" />
      <TouchButton label="3" code="Digit3" mode="tap" variant="emote" aria-label="Greet" :disabled="!proximityTargetId" />
      <TouchButton label="4" code="Digit4" mode="tap" variant="emote" aria-label="Invite to race" :disabled="!proximityTargetId" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import TouchButton from './TouchButton.vue'
import TouchJoystick from './TouchJoystick.vue'

export type TouchContext = 'garden-takeover' | 'race' | 'interior'

const props = withDefaults(defineProps<{
  context: TouchContext
  proximityTargetId?: string | null
}>(), {
  proximityTargetId: null,
})

const showSprint = computed(() => props.context === 'garden-takeover' || props.context === 'race')
const showJump = computed(() => props.context === 'garden-takeover' || props.context === 'race')
const showInteract = computed(() => props.context === 'garden-takeover' || props.context === 'interior')
const showMount = computed(() => props.context === 'garden-takeover')
const showEscape = computed(() => props.context === 'garden-takeover' || props.context === 'interior')
const showEmotes = computed(() => props.context === 'garden-takeover')
</script>

<style scoped>
.touch-controls {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 20;
  /* Keep native page scroll from stealing touches on iOS Safari. */
  touch-action: none;
  /* Reserve some room at the top for HUD elements. */
}

.touch-controls__right {
  position: absolute;
  right: calc(16px + env(safe-area-inset-right));
  bottom: calc(20px + env(safe-area-inset-bottom));
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  pointer-events: none; /* buttons inside flip this on */
}

.touch-controls__right > :deep(.touch-btn) {
  pointer-events: auto;
}

.touch-controls__exit {
  /* Detach from the flex stack and pin to the top-right of the viewport
     so "Esc" sits away from the primary action cluster. The negative
     right offset compensates for the flex item's implicit parent right. */
  position: absolute;
  top: calc(16px + env(safe-area-inset-top));
  right: 0;
}

.touch-controls__emotes {
  position: absolute;
  left: 50%;
  bottom: calc(16px + env(safe-area-inset-bottom));
  transform: translateX(-50%);
  display: flex;
  gap: 8px;
  padding: 8px 14px;
  border-radius: 999px;
  background: rgba(15, 20, 30, 0.45);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35);
  pointer-events: auto;
}

.touch-controls__emotes > :deep(.touch-btn) {
  pointer-events: auto;
}

/* Hide emote row on very narrow portrait screens so it doesn't collide
   with the joystick or action stack. */
@media (max-height: 520px) {
  .touch-controls__emotes { display: none; }
}
</style>
