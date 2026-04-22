<!--
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2026 Arun Rajkumar

  TouchButton — one on-screen button that dispatches synthetic keyboard
  events. Two modes:

  - tap:  fire keydown+keyup (one-frame apart) on pointerdown. For edge-
          triggered actions (E sit, V mount, 1–4 emotes, Escape).
  - hold: fire keydown on pointerdown, keyup on pointerup/cancel. For
          held actions (Shift sprint, Space while diving, etc.).

  Uses Pointer Events + setPointerCapture so the button keeps receiving
  events even if the finger slides off the element mid-press. Without
  capture, sliding a finger off a hold-button would leak a stuck
  keydown.
-->

<template>
  <button
    class="touch-btn"
    :class="[
      `touch-btn--${variant ?? 'default'}`,
      { 'touch-btn--pressed': pressed, 'touch-btn--disabled': disabled },
    ]"
    :aria-label="ariaLabel ?? label"
    :data-pressed="pressed || undefined"
    :data-disabled="disabled || undefined"
    @pointerdown="onPointerDown"
    @pointerup="onPointerUp"
    @pointercancel="onPointerUp"
    @pointerleave="onPointerLeave"
    @contextmenu.prevent
  >
    <span class="touch-btn__glyph">{{ label }}</span>
  </button>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { virtualKeyDown, virtualKeyTap, virtualKeyUp, type VirtualKeyName } from '@/utils/virtualKeyboard'

const props = defineProps<{
  label: string
  code: VirtualKeyName
  mode: 'tap' | 'hold'
  disabled?: boolean
  ariaLabel?: string
  /** Visual variant:
   *  - `primary` (default) — warm amber, used for V/E/Space action buttons.
   *  - `exit` — red accent for Esc.
   *  - `emote` — compact neutral style for 1/2/3/4 emote row.
   *  - `default` — old translucent glass (fallback).
   */
  variant?: 'primary' | 'exit' | 'emote' | 'default'
}>()

const pressed = ref(false)
const activePointerId = ref<number | null>(null)

function onPointerDown(event: PointerEvent): void {
  if (props.disabled) return
  event.preventDefault()
  // Capture so pointerup lands here even if the finger slides away.
  const target = event.currentTarget as HTMLElement
  try { target.setPointerCapture(event.pointerId) } catch { /* some browsers disallow */ }
  activePointerId.value = event.pointerId

  if (props.mode === 'tap') {
    pressed.value = true
    virtualKeyTap(props.code)
    // Brief press flash, independent of the (one-frame) synthetic keyup.
    window.setTimeout(() => { pressed.value = false }, 120)
  } else {
    pressed.value = true
    virtualKeyDown(props.code)
  }
}

function onPointerUp(event: PointerEvent): void {
  if (activePointerId.value !== event.pointerId) return
  activePointerId.value = null
  if (props.mode === 'hold') {
    pressed.value = false
    virtualKeyUp(props.code)
  }
}

function onPointerLeave(event: PointerEvent): void {
  // Only release if pointer isn't captured (capture keeps events flowing
  // and pointerup handles release there).
  const target = event.currentTarget as HTMLElement
  if (activePointerId.value === event.pointerId && !target.hasPointerCapture?.(event.pointerId)) {
    onPointerUp(event)
  }
}
</script>

<style scoped>
/* Base button — game-themed bevel shared across variants. The color
   palette is swapped per variant; shadow/border-radius/typography
   stay consistent so the whole overlay reads as one control set. */
.touch-btn {
  --btn-size: 58px;
  --btn-fill-top: #f2c971;
  --btn-fill-mid: #d4a843;
  --btn-fill-bot: #a67d26;
  --btn-base-block: #6b4e12;
  --btn-rim: rgba(40, 24, 0, 0.7);
  --btn-text: #2a1a00;

  width: var(--btn-size);
  height: var(--btn-size);
  padding: 0;
  border: none;
  border-radius: 50%;
  font: 700 16px/1 system-ui, -apple-system, sans-serif;
  letter-spacing: 0.02em;
  color: var(--btn-text);
  background: linear-gradient(
    180deg,
    var(--btn-fill-top) 0%,
    var(--btn-fill-mid) 55%,
    var(--btn-fill-bot) 100%
  );
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.5),
    inset 0 -2px 0 rgba(0, 0, 0, 0.2),
    0 3px 0 var(--btn-base-block),
    0 5px 10px rgba(0, 0, 0, 0.5),
    0 0 0 1.5px var(--btn-rim);
  cursor: pointer;
  user-select: none;
  -webkit-user-select: none;
  -webkit-tap-highlight-color: transparent;
  touch-action: none;
  text-shadow: 0 1px 0 rgba(255, 255, 255, 0.3);
  transition: transform 80ms ease, filter 120ms ease;
}

.touch-btn--pressed {
  transform: translateY(2px);
  filter: brightness(1.1);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.35),
    inset 0 -1px 0 rgba(0, 0, 0, 0.25),
    0 1px 0 var(--btn-base-block),
    0 2px 6px rgba(0, 0, 0, 0.4),
    0 0 0 1.5px var(--btn-rim),
    0 0 14px rgba(255, 208, 110, 0.55);
}

.touch-btn--disabled {
  opacity: 0.4;
  pointer-events: none;
  filter: saturate(0.3);
}

.touch-btn__glyph {
  display: inline-block;
  line-height: 1;
}

/* ── Variants ─────────────────────────────────────────── */

/* Primary action buttons (V, E, ⤒, Shift) — warm amber. Same palette
   as the "Take control" entry button so the whole overlay feels
   coherent. */
.touch-btn--primary {
  /* uses the defaults above */
}

/* Exit — red with dark rim, for Esc. Stays chunky but reads as
   "destructive / stop" without being visually shouty. */
.touch-btn--exit {
  --btn-size: 48px;
  --btn-fill-top: #ff6b6b;
  --btn-fill-mid: #e53935;
  --btn-fill-bot: #a71d1d;
  --btn-base-block: #5a0f0f;
  --btn-rim: rgba(60, 5, 5, 0.85);
  --btn-text: #fff;
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
  text-shadow: 0 1px 1px rgba(0, 0, 0, 0.5);
}

/* Emote row (1/2/3/4) — compact, neutral-to-cool so the important
   primary buttons pull the eye first. */
.touch-btn--emote {
  --btn-size: 44px;
  --btn-fill-top: #5a6a7a;
  --btn-fill-mid: #3a4855;
  --btn-fill-bot: #252f38;
  --btn-base-block: #11171d;
  --btn-rim: rgba(212, 168, 67, 0.55);
  --btn-text: #ffd764;
  font-size: 14px;
  text-shadow: 0 1px 1px rgba(0, 0, 0, 0.5);
}

/* Fallback / legacy — translucent glass (kept so existing callsites
   that pass no variant still render sensibly). */
.touch-btn--default {
  --btn-fill-top: rgba(255, 255, 255, 0.14);
  --btn-fill-mid: rgba(255, 255, 255, 0.10);
  --btn-fill-bot: rgba(255, 255, 255, 0.06);
  --btn-base-block: rgba(0, 0, 0, 0.4);
  --btn-rim: rgba(255, 255, 255, 0.22);
  --btn-text: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(10px) saturate(140%);
  -webkit-backdrop-filter: blur(10px) saturate(140%);
}
</style>
