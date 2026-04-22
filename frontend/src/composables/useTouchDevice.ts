// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * useTouchDevice — reactive touch-capability detection.
 *
 * Aligned with PlayCanvas's forum-accepted pattern: "Show touch UI if
 * touch is detected, hide it when keyboard input begins being used."
 * Hybrid devices (Surface, iPad + keyboard, Chromebook) can switch input
 * mode mid-session, so detection is adaptive rather than one-shot.
 *
 * Initial value: true when any of
 *   (a) `(pointer: coarse)` media query matches,
 *   (b) `navigator.maxTouchPoints > 0`,
 *   (c) the Touch Events API exposes `ontouchstart`.
 *
 * Runtime adaptation:
 *   - any `touchstart` or `pointerdown` with pointerType='touch' → true
 *   - a `mousemove` with non-zero delta → false
 * The non-zero-delta guard is important because iOS Safari fires a
 * synthesised `mousemove` after every `touchstart` for web-compat; the
 * delta is 0/0 on those synthetic events and a real mouse movement
 * never is.
 *
 * A manual override ref lets a settings toggle (or URL param) pin the
 * overlay on/off for testing and for users whose device misreports.
 */

import { computed, onBeforeUnmount, onMounted, ref, type ComputedRef, type Ref } from 'vue'

export type TouchOverride = 'auto' | 'on' | 'off'

interface UseTouchDeviceReturn {
  isTouch: ComputedRef<boolean>
  override: Ref<TouchOverride>
}

function detectInitial(): boolean {
  if (typeof window === 'undefined') return false
  try {
    if (window.matchMedia('(pointer: coarse)').matches) return true
  } catch {
    // older browsers without matchMedia — fall through
  }
  if (navigator.maxTouchPoints && navigator.maxTouchPoints > 0) return true
  if ('ontouchstart' in window) return true
  return false
}

export function useTouchDevice(): UseTouchDeviceReturn {
  const auto = ref(detectInitial())
  const override = ref<TouchOverride>('auto')

  const isTouch = computed(() =>
    override.value === 'on' ? true
    : override.value === 'off' ? false
    : auto.value,
  )

  const onTouchStart = (): void => {
    if (!auto.value) auto.value = true
  }
  const onPointerDown = (e: PointerEvent): void => {
    if (e.pointerType === 'touch' && !auto.value) auto.value = true
  }
  const onMouseMove = (e: MouseEvent): void => {
    // Ignore the synthetic zero-delta mousemove iOS Safari fires after
    // each touchstart. A real mouse produces non-zero movement.
    if (e.movementX === 0 && e.movementY === 0) return
    if (auto.value) auto.value = false
  }

  onMounted(() => {
    window.addEventListener('touchstart', onTouchStart, { passive: true })
    window.addEventListener('pointerdown', onPointerDown, { passive: true })
    window.addEventListener('mousemove', onMouseMove, { passive: true })
  })

  onBeforeUnmount(() => {
    window.removeEventListener('touchstart', onTouchStart)
    window.removeEventListener('pointerdown', onPointerDown)
    window.removeEventListener('mousemove', onMouseMove)
  })

  return { isTouch, override }
}
