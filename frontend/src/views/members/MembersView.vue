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

<!-- Members: People, Teams and Roles tabs. The tab lives in ``?tab=`` so
     a reload or shared link keeps the view. Each tab carries its own one
     primary action: Add member here, New team and Create role in theirs. -->
<template>
  <AppPage title="Members" :subtitle="membersSubtitle(store.members)">
    <template v-if="tab === 'people'" #actions>
      <v-tooltip v-if="githubConnected && !githubOrgConfigured" location="bottom" max-width="280">
        <template #activator="{ props: tip }">
          <span v-bind="tip"><v-btn variant="text" prepend-icon="mdi-github" disabled>Import from GitHub</v-btn></span>
        </template>
        Set your GitHub organization name in Settings to import members.
      </v-tooltip>
      <v-btn v-else-if="githubConnected" variant="text" prepend-icon="mdi-github" @click="importOpen = true">
        Import from GitHub
      </v-btn>
      <v-btn v-if="store.members.length >= 2" variant="text" @click="mergeOpen = true">Merge duplicates</v-btn>
      <v-btn color="primary" variant="flat" prepend-icon="mdi-account-plus-outline" @click="addOpen = true">Add member</v-btn>
    </template>

    <v-tabs v-model="tab" color="primary" density="compact" class="members-tabs" aria-label="Members sections">
      <v-tab value="people">People</v-tab>
      <v-tab value="teams">Teams</v-tab>
      <v-tab value="roles">Roles</v-tab>
    </v-tabs>

    <AppCallout v-if="store.error" variant="error">{{ store.error }}</AppCallout>

    <MembersPeopleTab v-if="tab === 'people'" />
    <MembersTeamsTab v-else-if="tab === 'teams'" />
    <MembersRolesTab v-else />

    <AddMemberDialog v-model="addOpen" />
    <GithubImportDialog v-model="importOpen" />
    <MergeMembersDialog v-model="mergeOpen" />
  </AppPage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPage from '@/components/common/AppPage.vue'
import AddMemberDialog from '@/components/members/AddMemberDialog.vue'
import GithubImportDialog from '@/components/members/GithubImportDialog.vue'
import MembersPeopleTab from '@/components/members/MembersPeopleTab.vue'
import MembersRolesTab from '@/components/members/MembersRolesTab.vue'
import MembersTeamsTab from '@/components/members/MembersTeamsTab.vue'
import MergeMembersDialog from '@/components/members/MergeMembersDialog.vue'
import { useMembersStore } from '@/stores/members'
import { useSettingsStore } from '@/stores/settings'
import { membersSubtitle } from '@/utils/members'

type MembersTab = 'people' | 'teams' | 'roles'
const TABS: MembersTab[] = ['people', 'teams', 'roles']

const route = useRoute()
const router = useRouter()
const store = useMembersStore()
const settingsStore = useSettingsStore()

const queryTab = route.query.tab as MembersTab
const tab = ref<MembersTab>(TABS.includes(queryTab) ? queryTab : 'people')
watch(tab, next => {
  // ``replace`` so switching tabs does not pile up browser history.
  void router.replace({ query: { ...route.query, tab: next === 'people' ? undefined : next } })
})

const addOpen = ref(false)
const importOpen = ref(false)
const mergeOpen = ref(false)

const githubConnected = computed(() => !!settingsStore.connections.github?.enabled)
const githubOrgConfigured = computed(() => !!settingsStore.connections.github?.org)

onMounted(() => {
  void store.fetchMembers()
  void store.fetchRoles()
  void settingsStore.fetchConnections()
})
</script>

<style scoped>
.members-tabs {
  border-bottom: 1px solid rgb(var(--v-theme-rule));
}
</style>
