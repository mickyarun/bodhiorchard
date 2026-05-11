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
  <transition name="invite-slide">
    <div v-if="visible" class="invite">
      <RaceThemeBackdrop variant="narrow" />

      <!-- Checkered-flag accent strip on the left -->
      <div class="invite__accent" aria-hidden="true" />

      <!-- Countdown ring — visualizes the auto-dismiss window -->
      <div class="invite__ring" :aria-label="`Auto-dismiss in ${Math.ceil(remainingMs / 1000)}s`">
        <svg viewBox="0 0 64 64" class="invite__ring-svg">
          <circle class="invite__ring-track" cx="32" cy="32" r="28" />
          <circle
            class="invite__ring-arc"
            cx="32"
            cy="32"
            r="28"
            :style="{ strokeDashoffset: ringOffset }"
          />
        </svg>
        <div class="invite__ring-inner">
          <v-icon icon="mdi-flag-checkered" size="22" />
        </div>
      </div>

      <!-- Body -->
      <div class="invite__body">
        <div class="invite__eyebrow">
          <CheckerFlagIcon :size="12" />
          RACE INVITATION
          <span v-if="distanceLabel" class="invite__distance">{{ distanceLabel }}</span>
        </div>
        <div class="invite__title">
          <span class="invite__host">{{ hostName }}</span>
          <span class="invite__title-sub">wants to race you</span>
        </div>

        <div class="invite__actions">
          <button class="invite__accept" @click="onAccept">
            <v-icon icon="mdi-play" size="18" class="mr-1" />
            Accept
          </button>
          <button class="invite__dismiss" @click="onDismiss">
            Dismiss
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useNotificationStore } from '@/stores/notifications'
import type { AppNotification, RaceInviteMeta } from '@/types'
import RaceThemeBackdrop from './RaceThemeBackdrop.vue'
import CheckerFlagIcon from './CheckerFlagIcon.vue'

/** Auto-dismiss window — matches the step-8 plan (30s). */
const AUTO_DISMISS_MS = 30_000

const router = useRouter()
const store = useNotificationStore()

const current = ref<AppNotification | null>(null)
const autoDismissTimer = ref<number | null>(null)
const remainingMs = ref(AUTO_DISMISS_MS)
const remainingTimer = ref<number | null>(null)

const visible = computed(() => current.value !== null)

const meta = computed<RaceInviteMeta>(() => {
  const m = current.value?.meta
  return (m && typeof m === 'object' ? m : {}) as RaceInviteMeta
})

const hostName = computed(() => meta.value.hostName || deriveHostFromMessage() || 'A racer')
const distanceLabel = computed(() =>
  meta.value.distanceM ? `${meta.value.distanceM} m sprint` : '',
)

/** Fraction [0..1] of ring that should still be visible — drives the arc. */
const RING_CIRC = 2 * Math.PI * 28   // matches svg radius=28
const ringOffset = computed(() => {
  const progress = 1 - remainingMs.value / AUTO_DISMISS_MS
  return RING_CIRC * progress
})

/** Fallback if `meta.hostName` isn't present on older notifications. */
function deriveHostFromMessage(): string | null {
  const raw = current.value?.message ?? ''
  // Messages look like "Dave Chen invited you to a 100 m race".
  const match = raw.match(/^(.+?) invited you/i)
  return match ? match[1] : null
}

watch(
  () => store.items,
  (items) => {
    if (current.value) return
    const next = items.find(
      (n) => n.type === 'race_invite' && !n.isRead && !n.isDismissed,
    )
    if (next) showToast(next)
  },
  { deep: true, immediate: true },
)

onBeforeUnmount(() => {
  clearTimers()
})

function showToast(notif: AppNotification): void {
  current.value = notif
  remainingMs.value = AUTO_DISMISS_MS
  clearTimers()
  autoDismissTimer.value = window.setTimeout(() => {
    if (current.value?.id === notif.id) current.value = null
  }, AUTO_DISMISS_MS)
  // 100 ms cadence is smooth enough for the ring without burning CPU.
  const started = Date.now()
  remainingTimer.value = window.setInterval(() => {
    remainingMs.value = Math.max(0, AUTO_DISMISS_MS - (Date.now() - started))
  }, 100)
}

function clearTimers(): void {
  if (autoDismissTimer.value !== null) {
    window.clearTimeout(autoDismissTimer.value)
    autoDismissTimer.value = null
  }
  if (remainingTimer.value !== null) {
    window.clearInterval(remainingTimer.value)
    remainingTimer.value = null
  }
}

async function onAccept(): Promise<void> {
  const n = current.value
  if (!n) return
  clearTimers()
  current.value = null
  const target = n.deepLink
  await store.markRead(n.id)
  if (target) await router.push(target)
}

function onDismiss(): void {
  const n = current.value
  clearTimers()
  current.value = null
  if (n) void store.dismiss(n.id)
}
</script>

<style scoped>
.invite {
  position: fixed;
  right: 24px;
  top: 24px;
  z-index: 2000;
  display: grid;
  grid-template-columns: 6px auto 1fr;
  gap: 16px;
  min-width: 360px;
  max-width: 440px;
  padding: 16px 18px 16px 0;
  border-radius: 14px;
  border: 1px solid rgba(255, 215, 94, 0.25);
  background: linear-gradient(180deg, #0f1726 0%, #0a0f1a 100%);
  color: #fff;
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
  box-shadow:
    0 24px 48px rgba(0, 0, 0, 0.45),
    0 0 32px rgba(255, 215, 94, 0.12);
  overflow: hidden;
  isolation: isolate;
}

/* Backdrop provided by <RaceThemeBackdrop variant="narrow" />. */
.invite > *:not(.race-theme-backdrop) { position: relative; z-index: 1; }

/* Left accent strip — animated checkered gradient suggests a start line */
.invite__accent {
  background-image:
    linear-gradient(45deg, #fff 25%, transparent 25%),
    linear-gradient(-45deg, #fff 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, #fff 75%),
    linear-gradient(-45deg, transparent 75%, #fff 75%);
  background-size: 6px 6px;
  background-position: 0 0, 0 3px, 3px -3px, -3px 0;
  background-color: #111;
  height: 100%;
}

/* Countdown ring wrapping the checkered-flag icon */
.invite__ring {
  position: relative;
  width: 64px;
  height: 64px;
  align-self: center;
  margin-left: 16px;
  flex-shrink: 0;
}
.invite__ring-svg {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}
.invite__ring-track {
  fill: none;
  stroke: rgba(255, 255, 255, 0.08);
  stroke-width: 4;
}
.invite__ring-arc {
  fill: none;
  stroke: #ffd75e;
  stroke-width: 4;
  stroke-linecap: round;
  stroke-dasharray: 175.93;  /* 2π·28 */
  transition: stroke-dashoffset 0.1s linear;
  filter: drop-shadow(0 0 4px rgba(255, 215, 94, 0.55));
}
.invite__ring-inner {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffd75e;
}

/* Body */
.invite__body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 4px 0;
}
.invite__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: rgba(255, 215, 94, 0.9);
  margin-bottom: 2px;
}
.invite__distance {
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(255, 215, 94, 0.14);
  color: #ffd75e;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.invite__title {
  font-size: 17px;
  font-weight: 700;
  letter-spacing: -0.01em;
  line-height: 1.25;
}
.invite__host {
  font-size: 20px;
  font-weight: 800;
  font-style: italic;
}
.invite__title-sub {
  display: block;
  font-weight: 500;
  opacity: 0.7;
  font-size: 13px;
  font-style: normal;
  margin-top: 1px;
}

.invite__actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.invite__accept {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 8px 18px;
  border: none;
  border-radius: 8px;
  background: linear-gradient(135deg, #30d66d, #19a34f);
  color: #06130b;
  font-family: inherit;
  font-weight: 800;
  font-size: 13px;
  letter-spacing: 0.04em;
  cursor: pointer;
  box-shadow: 0 6px 16px rgba(47, 216, 107, 0.3);
  transition: filter 0.15s, transform 0.15s;
}
.invite__accept:hover { filter: brightness(1.08); transform: translateY(-1px); }
.invite__dismiss {
  padding: 8px 14px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  background: transparent;
  color: rgba(255, 255, 255, 0.7);
  font-family: inherit;
  font-weight: 600;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}
.invite__dismiss:hover {
  background: rgba(255, 255, 255, 0.06);
  color: #fff;
}

/* Slide-in/out transition */
.invite-slide-enter-active, .invite-slide-leave-active {
  transition: transform 0.28s ease, opacity 0.28s ease;
}
.invite-slide-enter-from, .invite-slide-leave-to {
  transform: translateX(32px);
  opacity: 0;
}
</style>
