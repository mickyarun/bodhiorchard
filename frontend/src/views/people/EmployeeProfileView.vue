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

<!-- One employee record: /people/:userId, or the caller's own at
     /me/profile ("My details"). The first tab sits beside a side column
     with leave, team and dates; the others take the full width. -->
<template>
  <div class="profile">
    <nav v-if="!isOwn && canViewEmployees" aria-label="Breadcrumb" class="profile__crumbs">
      <router-link :to="{ name: 'employees' }">Employees</router-link>
      <span aria-hidden="true">/</span>
      <span aria-current="page">{{ record?.name ?? '' }}</span>
    </nav>

    <v-progress-linear v-if="store.loading" indeterminate color="primary" />

    <template v-else-if="store.error">
      <AppCallout :variant="isOwn && store.errorStatus === 404 ? 'info' : 'error'">
        {{ store.error }}
      </AppCallout>
      <OwnPhotoCard v-if="isOwn && store.errorStatus === 404" />
    </template>

    <template v-else-if="record">
      <AppCallout v-if="avatarError" variant="error">{{ avatarError }}</AppCallout>
      <EmployeeHeaderCard :record="record" @avatar-updated="onAvatarUpdated" @avatar-error="avatarError = $event">
        <template #actions>
          <EmployeePasswordButton
            v-if="record.access.reset_password"
            :key="record.user_id"
            :user-id="record.user_id"
            :name="record.name"
          />
        </template>
      </EmployeeHeaderCard>

      <v-tabs
        v-model="tab"
        color="primary"
        slider-color="primary"
        show-arrows
        class="profile__tabs"
        aria-label="Profile sections"
      >
        <v-tab v-for="item in tabs" :key="item.value" :value="item.value">
          <v-icon v-if="item.locked" icon="mdi-lock-outline" size="14" class="mr-1" />
          {{ item.label }}
        </v-tab>
      </v-tabs>

      <div class="profile__body" :class="{ 'profile__body--aside': showAside }">
        <v-tabs-window v-model="tab" class="profile__main">
          <v-tabs-window-item v-if="record.personal" value="personal">
            <PersonalTab :employee-id="record.user_id" :personal="record.personal" :mode="personalMode" :is-self="isOwn" />
          </v-tabs-window-item>
          <v-tabs-window-item value="employment">
            <EmploymentTab :record="record" />
          </v-tabs-window-item>
          <v-tabs-window-item v-if="has('leave')" value="leave">
            <div class="profile__panel"><MemberLeaveTab :user-id="record.user_id" /></div>
          </v-tabs-window-item>
          <v-tabs-window-item v-if="has('bank')" value="bank">
            <BankIdsTab :user-id="record.user_id" :is-own="isOwn" />
          </v-tabs-window-item>
          <v-tabs-window-item v-if="has('documents')" value="documents">
            <DocumentsTab :user-id="record.user_id" />
          </v-tabs-window-item>
        </v-tabs-window>
        <!-- Hidden, not removed, on the other tabs: it keeps what it loaded. -->
        <ProfileAside
          v-show="showAside"
          :record="record"
          :show-leave="showLeave"
          @leave-details="tab = 'leave'"
        />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppCallout from '@/components/common/AppCallout.vue'
import MemberLeaveTab from '@/components/leave/MemberLeaveTab.vue'
import BankIdsTab from '@/components/people/BankIdsTab.vue'
import DocumentsTab from '@/components/people/DocumentsTab.vue'
import EmployeeHeaderCard from '@/components/people/EmployeeHeaderCard.vue'
import EmployeePasswordButton from '@/components/people/EmployeePasswordButton.vue'
import EmploymentTab from '@/components/people/EmploymentTab.vue'
import PersonalTab from '@/components/people/PersonalTab.vue'
import OwnPhotoCard from '@/components/people/profile/OwnPhotoCard.vue'
import ProfileAside from '@/components/people/profile/ProfileAside.vue'
import { usePermissions } from '@/composables/usePermissions'
import { useProfileAccess } from '@/composables/useProfileAccess'
import { useAuthStore } from '@/stores/auth'
import { useEmployeesStore } from '@/stores/employees'
import type { ProfileTab } from '@/utils/employeeProfile'

const route = useRoute()
const store = useEmployeesStore()
const authStore = useAuthStore()
const { canViewEmployees } = usePermissions()

const routeUserId = computed(() => route.params.userId as string | undefined)
const isOwn = computed(() => !routeUserId.value || routeUserId.value === authStore.user?.id)
const record = computed(() => store.record)
const { showLeave, personalMode, tabs } = useProfileAccess(record, isOwn)
const tab = ref<ProfileTab>('personal')
const avatarError = ref('')

const has = (value: ProfileTab) => tabs.value.some(t => t.value === value)
// The side column belongs to the first tab, the profile's overview.
const showAside = computed(() => tab.value === tabs.value[0]?.value)

/**
 * Keep the loaded record in step with the photo the child just changed,
 * so the header and the directory agree without a refetch — and, on your
 * own profile, the top bar too.
 */
function onAvatarUpdated(avatarUrl: string | null): void {
  avatarError.value = ''
  if (store.record) store.record.avatar_url = avatarUrl
  if (isOwn.value) authStore.setAvatarUrl(avatarUrl)
}

watch(
  () => routeUserId.value,
  async userId => {
    // A photo error belongs to the profile it happened on.
    avatarError.value = ''
    await store.fetchRecord(userId && !isOwn.value ? userId : 'me')
    tab.value = store.record?.personal ? 'personal' : 'employment'
  },
  { immediate: true },
)
</script>

<style scoped>
.profile {
  padding: 22px 36px 40px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
  container-type: inline-size;
}
.profile__crumbs {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.profile__crumbs a {
  color: var(--color-accent-text);
  font-weight: 500;
  text-decoration: none;
}
.profile__crumbs a:hover {
  text-decoration: underline;
}
.profile__tabs {
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}
.profile__body {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}
.profile__main {
  min-width: 0;
}
.profile__panel {
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
  padding: 20px;
}
@container (min-width: 900px) {
  .profile__body--aside {
    grid-template-columns: minmax(0, 1fr) 340px;
  }
}
@media (max-width: 600px) {
  .profile {
    padding: 20px 16px 32px;
  }
  .profile__panel {
    padding: 16px;
  }
}
</style>
