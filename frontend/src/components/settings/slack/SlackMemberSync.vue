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

<!-- Link Slack workspace people to Glideship members, or import them as
     new members. Nothing changes until Save. -->
<template>
  <section class="sync" aria-labelledby="slack-sync-title">
    <div class="sync__head">
      <h3 id="slack-sync-title" class="sync__title">Sync members</h3>
      <div class="sync__head-actions">
        <!-- Linking and importing bring photos in already; this catches
             up members linked before that, or who added a photo since. -->
        <v-btn
          v-if="canImportSlackPhotos"
          variant="text"
          size="small"
          prepend-icon="mdi-account-box-outline"
          :loading="photos.importing.value"
          @click="photos.run()"
        >
          Import photos
        </v-btn>
        <v-btn variant="outlined" size="small" prepend-icon="mdi-sync" :loading="s.syncing.value" @click="s.sync()">Fetch from Slack</v-btn>
      </div>
    </div>
    <AppCallout v-if="photos.outcome.value" :variant="photos.outcome.value.variant" class="mt-3">
      {{ photos.outcome.value.text }}
    </AppCallout>
    <p class="sync__note">
      Needs the <code v-for="scope in SLACK_SYNC_SCOPES" :key="scope" class="mr-1">{{ scope }}</code> bot scopes.
    </p>

    <AppCallout v-if="s.error.value" variant="error" class="mb-3">{{ s.error.value }}</AppCallout>
    <AppCallout v-if="s.success.value" variant="success" class="mb-3">{{ s.success.value }}</AppCallout>

    <template v-if="s.members.value.length > 0">
      <ul class="sync__list">
        <li v-for="m in s.members.value" :key="m.slack_id" class="sync__row">
          <span class="sync__who">
            <v-avatar v-if="m.slack_avatar" size="32"><v-img :src="m.slack_avatar" alt="" referrerpolicy="no-referrer" cover /></v-avatar>
            <AppMonogram v-else :name="m.slack_name" />
            <span class="sync__name">
              <span>{{ m.slack_name }}</span>
              <span v-if="m.slack_email" class="sync__email">{{ m.slack_email }}</span>
            </span>
          </span>
          <span v-if="m.already_linked" class="sync__action">
            <span class="sync__linked">Linked to {{ m.matched_user_name }}</span>
            <v-btn icon="mdi-link-variant-off" size="small" variant="text" :aria-label="`Unlink ${m.slack_name}`" @click="s.unlink(m.slack_id)" />
          </span>
          <span v-else class="sync__action">
            <AppPillToggle
              :model-value="s.actionFor(m.slack_id)"
              :options="ACTION_OPTIONS"
              size="sm"
              :aria-label="`What to do with ${m.slack_name}`"
              @update:model-value="(a: SlackAction) => s.setAction(m.slack_id, a)"
            />
            <v-autocomplete
              v-if="s.actionFor(m.slack_id) === 'link'"
              :model-value="s.links.value[m.slack_id] ?? null"
              :items="memberPickerItems(membersStore.members)"
              :label="`Member for ${m.slack_name}`"
              density="compact"
              variant="outlined"
              hide-details
              clearable
              auto-select-first
              class="sync__picker"
              @update:model-value="(id: string | null) => s.setLink(m.slack_id, id)"
            />
            <v-btn icon="mdi-close" size="small" variant="text" :aria-label="`Skip ${m.slack_name}`" @click="s.dismiss(m.slack_id)" />
          </span>
        </li>
      </ul>

      <AppCallout v-if="s.importWithoutEmail.value > 0" variant="warning" class="mt-3">
        {{ plural(s.importWithoutEmail.value, 'person', 'people') }} set to import have no email. Add
        <strong>users:read.email</strong> to the Slack app's Bot Token Scopes, reinstall it, then fetch again.
      </AppCallout>

      <div class="sync__foot">
        <span class="sync__counts">{{ s.toLink.value.length }} to link · {{ s.toImport.value.length }} to import</span>
        <v-btn
          variant="outlined"
          :loading="s.saving.value"
          :disabled="s.toLink.value.length === 0 && s.toImport.value.length === 0"
          @click="s.save()"
        >
          Save member changes
        </v-btn>
      </div>
    </template>
    <p v-else-if="!s.syncing.value" class="sync__note">Fetch from Slack to see the workspace's people.</p>
  </section>
</template>

<script setup lang="ts">
import AppCallout from '@/components/common/AppCallout.vue'
import AppMonogram from '@/components/common/AppMonogram.vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import { useSlackMemberSync, type SlackAction } from '@/composables/useSlackMemberSync'
import { usePermissions } from '@/composables/usePermissions'
import { useSlackPhotoImport } from '@/composables/useSlackPhotoImport'
import { useMembersStore } from '@/stores/members'
import { plural } from '@/utils/format'
import { memberPickerItems } from '@/utils/members'
import { SLACK_SYNC_SCOPES } from '@/utils/slackManifest'

const ACTION_OPTIONS: { label: string; value: SlackAction }[] = [
  { label: 'Link', value: 'link' },
  { label: 'Import', value: 'import' },
]

const s = useSlackMemberSync()
const photos = useSlackPhotoImport()
const { canImportSlackPhotos } = usePermissions()
const membersStore = useMembersStore()
</script>

<style scoped>
.sync {
  padding: 16px;
  border-radius: 10px;
  border: 1px solid rgb(var(--v-theme-rule));
}
.sync__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.sync__head-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 4px;
}
.sync__title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}
.sync__note {
  margin: 6px 0 12px;
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.sync__list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.sync__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 12px;
  padding: 10px 0;
  border-top: 1px solid var(--color-rule-2);
}
.sync__who {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.sync__name {
  display: flex;
  flex-direction: column;
  font-size: 14px;
  min-width: 0;
}
.sync__email,
.sync__counts {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
  overflow-wrap: anywhere;
}
.sync__action {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sync__linked {
  font-size: 13px;
  color: rgb(var(--v-theme-ink-2));
}
.sync__picker {
  width: 220px;
}
.sync__foot {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 12px;
}
@media (max-width: 600px) {
  .sync__picker {
    width: 100%;
    min-width: 160px;
  }
}
</style>
