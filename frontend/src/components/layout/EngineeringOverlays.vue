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

<!-- Layout-wide toasts, banners and dialogs for engineering-workspace
     features (XP, races, backlash, agent jobs, yield offers). Mounted
     only for members with engineering access, so people-only roles never
     open their sockets or call their APIs. -->
<template>
  <!-- Real-time XP toast notifications -->
  <XPToast
    :toasts="xpToasts"
    @dismiss="xpDismiss"
  />

  <!-- Race invite toast + watch banner — both mount layout-wide so they
       survive route changes while the user is signed in. -->
  <RaceInviteToast />
  <BacklashInviteToast />
  <RaceWatchBanner />

  <!-- Cross-BUD job-completion toast. Surfaces when a chat / agent
       job finishes for a BUD the user is NOT currently on. The
       "snapped back to previous BUD" bug was *perceived* as
       auto-nav; replacing implicit jumps with this explicit Review
       CTA closes that class of complaint. Reads the existing
       notifications store, no extra socket subscriptions. -->
  <ChatCompletionToast />

  <!-- Yield-offer reject / reassign confirmation dialogs. Lifted out
       of NotificationBell so the bell stays single-root and v-show
       on it doesn't trip Vue's "runtime directive on fragment" warn.
       The shared composable wires the bell-row triggers to these
       modals; v-dialog teleports to body so co-location doesn't
       matter for the rendered DOM. -->
  <YieldOfferDialogs />
</template>

<script setup lang="ts">
import XPToast from '@/components/common/XPToast.vue'
import ChatCompletionToast from '@/components/common/ChatCompletionToast.vue'
import YieldOfferDialogs from '@/components/common/YieldOfferDialogs.vue'
import RaceInviteToast from '@/components/race/RaceInviteToast.vue'
import BacklashInviteToast from '@/components/backlash/BacklashInviteToast.vue'
import RaceWatchBanner from '@/components/race/RaceWatchBanner.vue'
import { useXPSocket } from '@/composables/useXPSocket'

// Real-time XP notifications for every engineering page.
const { toasts: xpToasts, dismissToast: xpDismiss } = useXPSocket()
</script>
