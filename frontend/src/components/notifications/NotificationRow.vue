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

<!-- One notification in the tray. The whole row opens it (the title is a
     button stretched over the row); its own actions sit above that and
     show on hover or keyboard focus. Touch screens get Dismiss only. An invite
     that can be declined gets a Decline button under the text. -->
<template>
  <li class="n-row" :class="{ 'n-row--unread': !notif.isRead }">
    <span class="n-row__icon" :class="`n-row__icon--${visual.tone}`" aria-hidden="true">
      <v-icon :icon="visual.icon" size="18" />
      <span v-if="!notif.isRead" class="n-row__dot" />
    </span>

    <div class="n-row__text">
      <button type="button" class="n-row__open" :aria-describedby="describedBy" @click="emit('open')">
        <span class="n-row__title">{{ notif.title }}</span>
        <span v-if="!notif.isRead" class="d-sr-only">, unread</span>
      </button>
      <p v-if="notif.message" :id="bodyId" class="n-row__body">{{ notif.message }}</p>
      <span :id="timeId" class="n-row__time">{{ relativeTime(notif.createdAt, now, SHORT_AGO) }}</span>
      <div v-if="invite" class="n-row__inline">
        <v-btn
          size="small"
          variant="outlined"
          :loading="declining"
          :disabled="declining"
          @click="emit('decline', invite)"
        >
          Decline invite
        </v-btn>
      </div>
    </div>

    <div class="n-row__actions">
      <v-btn
        v-if="notif.deepLink"
        class="n-row__open-action"
        icon="mdi-arrow-right"
        variant="text"
        size="small"
        density="comfortable"
        :aria-label="`Open: ${notif.title}`"
        @click="emit('open')"
      />
      <v-btn
        icon="mdi-close"
        variant="text"
        size="small"
        density="comfortable"
        :aria-label="`Dismiss: ${notif.title}`"
        :disabled="declining"
        @click="emit('dismiss')"
      />
    </div>
  </li>
</template>

<script setup lang="ts">
import { computed, useId } from 'vue'
import type { AppNotification } from '@/types'
import { SHORT_AGO, relativeTime } from '@/utils/date'
import { declinableInvite, notificationVisual, type DeclinableInvite } from '@/utils/notificationVisuals'

const props = defineProps<{
  notif: AppNotification
  viewerId: string
  now: Date
  declining: boolean
}>()

const emit = defineEmits<{ open: []; dismiss: []; decline: [kind: DeclinableInvite] }>()

const visual = computed(() => notificationVisual(props.notif.type))
const invite = computed(() => declinableInvite(props.notif, props.viewerId))

// The title button is the row's name; its body and time describe it.
const bodyId = useId()
const timeId = useId()
const describedBy = computed(() => (props.notif.message ? `${bodyId} ${timeId}` : timeId))
</script>

<style scoped src="./notification-row.css"></style>
