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
<!-- HR configuration for birthday and work-anniversary Slack announcements. -->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import AppCallout from '@/components/common/AppCallout.vue'
import SettingsPageShell from '@/components/settings/SettingsPageShell.vue'
import { usePermissions } from '@/composables/usePermissions'
import { useCelebrationsStore } from '@/stores/celebrations'
import type { CelebrationSettings, GifRating, WeekendPolicy } from '@/types/celebrations'
import { WEEKDAY_ITEMS } from '@/utils/schedule'
import { timezoneOptions } from '@/utils/timezones'

const store = useCelebrationsStore()
// Where posts go, and whether they ping everyone, is an admin/owner call;
// HR can tune everything else. The backend enforces this — the disabled
// fields just avoid offering a save that would be refused.
const { canControlCelebrationChannel } = usePermissions()
const CHANNEL_LOCKED_HINT = 'Only an admin or the org owner can change this.'
const saveSuccess = ref(false)
const notice = ref('')
const noticeVariant = ref<'info' | 'success' | 'warning'>('info')


const WEEKEND_POLICIES: { title: string; value: WeekendPolicy; subtitle: string }[] = [
  {
    title: 'Celebrate on the next posting day',
    value: 'roll_forward',
    subtitle: 'A Saturday birthday is announced on Monday.',
  },
  {
    title: 'Celebrate early',
    value: 'roll_backward',
    subtitle: 'A Saturday birthday is announced on Friday.',
  },
  {
    title: 'Skip it',
    value: 'skip',
    subtitle: 'Celebrations on non-posting days are never announced.',
  },
]

const GIF_RATINGS: { title: string; value: GifRating }[] = [
  { title: 'G — safest', value: 'g' },
  { title: 'PG', value: 'pg' },
  { title: 'PG-13', value: 'pg-13' },
]


const form = ref<CelebrationSettings | null>(null)

/**
 * The weekend policy only means anything when some days are excluded —
 * on the default all-day schedule nothing is ever skipped, so showing the
 * question would imply a choice that has no effect.
 */
const hasSkippedDays = computed(() => (form.value?.activeWeekdays.length ?? 7) < 7)

/** Mirrors the backend's model validator so the save button gates locally. */
const valid = computed(() => {
  const f = form.value
  if (!f) return false
  if (f.activeWeekdays.length === 0) return false
  if (!f.enabled) return true
  return !!f.slackChannelId && (f.includeBirthdays || f.includeAnniversaries)
})

/** Human-readable outcomes for the sample-post reason codes. */
const TEST_MESSAGES: Record<string, string> = {
  no_channel: 'Set a Slack channel first.',
  no_slack_token: 'Connect Slack in Settings → Connections first.',
  token_decrypt_failed: 'The stored Slack token could not be read. Re-connect Slack.',
  'slack:channel_not_found': "Slack can't find that channel. Check the channel ID.",
  'slack:not_in_channel': 'The bot is not in that channel yet. Invite it, then try again.',
  'slack:is_archived': 'That channel is archived.',
  'slack:invalid_auth': 'The Slack token is no longer valid. Re-connect Slack.',
  'slack:ratelimited': 'Slack is rate-limiting the bot. Try again in a minute.',
}

/** "This will announce 42 birthdays and 57 work anniversaries." */
const audienceLine = computed(() => {
  const a = store.audience
  if (!a) return ''
  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`
  return (
    `Switching this on announces ${plural(a.birthdays, 'birthday', 'birthdays')} and ` +
    `${plural(a.anniversaries, 'work anniversary', 'work anniversaries')} across the year — ` +
    'everyone with a date on file who has not muted it.'
  )
})

async function load(): Promise<void> {
  await Promise.all([store.fetchSettings(), store.fetchAudience()])
  if (store.settings) form.value = { ...store.settings }
}

async function save(): Promise<void> {
  if (!form.value || !valid.value) return
  if (await store.saveSettings(form.value)) saveSuccess.value = true
}

async function sendTest(): Promise<void> {
  if (!form.value) return
  notice.value = ''
  const result = await store.sendTest(form.value)
  if (!result) return
  if (result.posted) {
    noticeVariant.value = 'success'
    notice.value =
      'Sample posted with you as the celebrant. Check the channel — the real ' +
      "schedule hasn't been touched."
    return
  }
  noticeVariant.value = 'warning'
  notice.value = TEST_MESSAGES[result.detail] ?? `Slack didn't accept the post (${result.detail}).`
}

async function syncAvatars(): Promise<void> {
  notice.value = ''
  const result = await store.syncSlackAvatars()
  if (!result) return
  noticeVariant.value = result.updated ? 'success' : 'info'
  notice.value =
    `${result.updated} photo(s) imported. ` +
    `${result.skipped_has_photo} already had one, ` +
    `${result.skipped_no_photo} have no Slack photo.`
}

onMounted(load)
</script>

<template>
  <SettingsPageShell
    title="Celebrations"
    subtitle="Birthday and work-anniversary announcements in Slack."
    :loading="store.loading"
    :saving="store.saving"
    :valid="valid"
    :error="store.error || null"
    :save-success="saveSuccess"
    @save="save"
    @success-close="saveSuccess = false"
  >
    <AppCallout
      variant="info"
      eyebrow="How it works"
      icon="mdi-cake-variant-outline"
      class="mb-6"
    >
      One post per day to the channel below, covering everyone celebrating — weekends
      included, so a Saturday birthday is announced on the Saturday. Birthdays show the day
      and month only, never the year. Anyone can mute their own announcement from their
      profile, and dates come from their employee record.
    </AppCallout>

    <AppCallout v-if="audienceLine" variant="warning" eyebrow="Who gets announced" class="mb-6">
      {{ audienceLine }}
    </AppCallout>

    <AppCallout v-if="notice" :variant="noticeVariant" class="mb-6">
      {{ notice }}
    </AppCallout>

    <template v-if="form">
      <v-switch
        v-model="form.enabled"
        color="primary"
        label="Announce birthdays and work anniversaries"
        hide-details
        class="mb-4"
      />

      <v-text-field
        v-model="form.slackChannelId"
        label="Slack channel ID"
        placeholder="C0123456789"
        :disabled="!canControlCelebrationChannel"
        :hint="
          canControlCelebrationChannel
            ? 'Channel ID, not #name. Copy it from the channel\'s About tab, and invite the bot.'
            : CHANNEL_LOCKED_HINT
        "
        persistent-hint
        variant="outlined"
        density="comfortable"
        style="max-width: 420px"
        class="mb-6"
      />

      <div class="d-flex ga-4 mb-4 flex-wrap">
        <v-text-field
          v-model="form.postTime"
          type="time"
          label="Post time"
          variant="outlined"
          density="comfortable"
          style="max-width: 180px"
          hide-details
        />
        <v-autocomplete
          v-model="form.timezone"
          :items="timezoneOptions(form.timezone)"
          label="Timezone (blank = server)"
          clearable
          variant="outlined"
          density="comfortable"
          style="min-width: 260px"
          hide-details
        />
      </div>

      <v-select
        v-model="form.activeWeekdays"
        :items="WEEKDAY_ITEMS"
        label="Posting days"
        multiple
        chips
        variant="outlined"
        density="comfortable"
        hint="All seven by default, so a weekend birthday is posted that day."
        persistent-hint
        class="mb-6"
      />

      <v-select
        v-if="hasSkippedDays"
        v-model="form.weekendPolicy"
        :items="WEEKEND_POLICIES"
        item-title="title"
        item-value="value"
        label="When a celebration falls on a non-posting day"
        variant="outlined"
        density="comfortable"
        class="mb-6"
      >
        <template #item="{ props: itemProps, item }">
          <v-list-item v-bind="itemProps" :subtitle="item.raw.subtitle" />
        </template>
      </v-select>

      <div class="mb-2 text-body-2 text-medium-emphasis">What to announce</div>
      <v-switch
        v-model="form.includeBirthdays"
        color="primary"
        label="Birthdays"
        hide-details
      />
      <v-switch
        v-model="form.includeAnniversaries"
        color="primary"
        label="Work anniversaries"
        hide-details
        class="mb-4"
      />
      <v-switch
        v-model="form.mentionChannel"
        color="primary"
        label="Ping @channel"
        :disabled="!canControlCelebrationChannel"
        :hint="
          canControlCelebrationChannel
            ? 'Notifies everyone in the channel. Off by default.'
            : CHANNEL_LOCKED_HINT
        "
        persistent-hint
        class="mb-6"
      />

      <div class="mb-2 text-body-2 text-medium-emphasis">Celebration GIF</div>
      <v-switch
        v-model="form.gifEnabled"
        color="primary"
        label="Attach a random GIF from Giphy"
        hint="Needs GIPHY_API_KEY on the backend; posts go out text-only without it."
        persistent-hint
        class="mb-4"
      />
      <div v-if="form.gifEnabled" class="d-flex ga-4 mb-4 flex-wrap">
        <v-select
          v-model="form.gifRating"
          :items="GIF_RATINGS"
          label="Content rating"
          variant="outlined"
          density="comfortable"
          style="max-width: 220px"
          hide-details
        />
        <v-combobox
          v-model="form.gifTags"
          label="Search tags"
          multiple
          chips
          closable-chips
          variant="outlined"
          density="comfortable"
          style="min-width: 320px"
          hint="One is picked at random per post."
          persistent-hint
        />
      </div>
    </template>

    <template #header-actions>
      <v-btn
        variant="tonal"
        :loading="store.syncingAvatars"
        prepend-icon="mdi-account-box-outline"
        @click="syncAvatars"
      >
        Import photos from Slack
      </v-btn>
      <v-btn
        variant="tonal"
        :loading="store.testing"
        :disabled="!form?.slackChannelId"
        prepend-icon="mdi-send-outline"
        @click="sendTest"
      >
        Send sample post
      </v-btn>
    </template>
  </SettingsPageShell>
</template>
