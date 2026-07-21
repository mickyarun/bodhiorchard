<!--
  Copyright 2025-2026 Arun Rajkumar

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.
-->
<template>
  <transition name="backlash-toast">
    <aside v-if="current" class="invite" role="status" aria-live="polite">
      <div class="invite__board" aria-hidden="true">
        <span v-for="square in 16" :key="square" :class="{ dark: squarePattern(square) }" />
        <i class="piece piece--black" />
        <i class="piece piece--white" />
      </div>
      <div class="invite__body">
        <div class="invite__eyebrow">BACKLASH CHALLENGE</div>
        <strong>{{ hostName }}</strong>
        <span>wants to test your tactics.</span>
        <div class="invite__actions">
          <button class="accept" @click="accept">Accept duel</button>
          <button class="decline" :disabled="declining" @click="decline">
            {{ declining ? 'Declining…' : 'Decline' }}
          </button>
        </div>
      </div>
      <button class="invite__close" aria-label="Hide challenge" @click="hide">×</button>
    </aside>
  </transition>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useNotificationStore } from '@/stores/notifications'
import type { AppNotification, BacklashInviteMeta } from '@/types'
import { isInviteUnexpired } from '@/utils/inviteExpiry'

const store = useNotificationStore()
const router = useRouter()
const current = ref<AppNotification | null>(null)
const hiddenIds = new Set<string>()

const meta = computed(() => (current.value?.meta ?? {}) as BacklashInviteMeta)
const hostName = computed(() => meta.value.hostName?.trim() || 'A teammate')
const declining = computed(() => current.value
  ? store.pendingDeclineIds.has(current.value.id)
  : false)

watch(
  () => store.items,
  (items) => {
    if (current.value) return
    current.value = items.find((notification) =>
      !hiddenIds.has(notification.id) && isPendingBacklashInvite(notification),
    ) ?? null
  },
  { deep: true, immediate: true },
)

function isPendingBacklashInvite(notification: AppNotification): boolean {
  const payload = (notification.meta ?? {}) as BacklashInviteMeta
  return notification.type === 'minigame_invite'
    && payload.game === 'backlash'
    && !payload.declinedBy
    && isInviteUnexpired(payload.expiresAt)
    && !notification.isRead
    && !notification.isDismissed
}

function squarePattern(square: number): boolean {
  const index = square - 1
  return (Math.floor(index / 4) + index % 4) % 2 === 1
}

function hide(): void {
  if (current.value) hiddenIds.add(current.value.id)
  current.value = null
}

async function accept(): Promise<void> {
  const notification = current.value
  if (!notification) return
  current.value = null
  await store.markRead(notification.id)
  if (notification.deepLink) await router.push(notification.deepLink)
}

function decline(): void {
  const notification = current.value
  if (!notification || declining.value) return
  current.value = null
  void store.declineBacklashInvite(notification.id)
}
</script>

<style scoped>
.invite {
  position: fixed; z-index: 2050; top: 24px; right: 24px; display: grid;
  grid-template-columns: 112px minmax(210px, 1fr); width: min(430px, calc(100vw - 32px));
  overflow: hidden; border: 1px solid rgba(219, 153, 83, .45); border-radius: 18px;
  background: linear-gradient(135deg, #160f0c, #431d18); color: #fff5e2;
  box-shadow: 0 24px 60px rgba(0,0,0,.5), 0 0 30px rgba(171,67,41,.15);
}
.invite__board { position: relative; display: grid; grid-template-columns: repeat(4, 1fr); overflow: hidden; padding: 14px; background: #9b613d; }
.invite__board span { aspect-ratio: 1; background: #c99767; border: 1px solid rgba(43,22,13,.15); }
.invite__board span.dark { background: #714027; }
.piece { position: absolute; width: 31px; height: 31px; border-radius: 50%; border: 3px solid; box-shadow: 0 5px 8px rgba(0,0,0,.5), inset 0 0 0 3px rgba(255,255,255,.08); }
.piece--black { left: 24px; top: 27px; background: #171717; border-color: #302c29; }
.piece--white { right: 22px; bottom: 29px; background: #eee5d3; border-color: #fffaf0; }
.invite__body { position: relative; z-index: 1; display: flex; min-width: 0; flex-direction: column; padding: 18px 38px 17px 18px; }
.invite__eyebrow { color: #e3a55d; font-size: 9px; font-weight: 900; letter-spacing: .18em; }
.invite__body strong { margin-top: 4px; font-family: Georgia, serif; font-size: 22px; }
.invite__body > span { color: rgba(255,245,226,.65); font-size: 12px; }
.invite__actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 13px; }
.invite__actions button { border-radius: 8px; padding: 8px 13px; font-size: 12px; font-weight: 800; white-space: nowrap; cursor: pointer; }
.accept { border: 0; background: linear-gradient(135deg, #d0683c, #9c3028); color: white; }
.decline { border: 1px solid rgba(255,255,255,.16); background: transparent; color: rgba(255,255,255,.72); }
.decline:disabled { opacity: .5; }
.invite__close { position: absolute; top: 7px; right: 9px; border: 0; background: transparent; color: rgba(255,255,255,.5); font-size: 20px; cursor: pointer; }
.backlash-toast-enter-active, .backlash-toast-leave-active { transition: opacity .25s, transform .32s cubic-bezier(.2,.9,.25,1); }
.backlash-toast-enter-from, .backlash-toast-leave-to { opacity: 0; transform: translateX(35px) scale(.96); }
@media (max-width: 520px) {
  .invite { top: 12px; right: 16px; grid-template-columns: 82px 1fr; }
  .invite__board { padding: 9px; }
  .invite__body { padding-left: 14px; }
  .piece { width: 25px; height: 25px; }
}
</style>
