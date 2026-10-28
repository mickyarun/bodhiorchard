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

<!-- Top-right cluster: notifications, then the account menu. Both open
     downward from the top right. Shared by the desktop and phone bars. -->
<template>
  <div v-if="auth.user?.id" class="account-cluster">
    <NotificationBell :user-id="auth.user.id" />
    <AccountMenu />
  </div>
</template>

<script setup lang="ts">
import NotificationBell from '@/components/common/NotificationBell.vue'
import AccountMenu from '@/components/layout/AccountMenu.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
</script>

<style scoped>
.account-cluster {
  display: flex;
  align-items: center;
  /* Room for a two-digit unread badge beside the avatar. */
  gap: 8px;
}
</style>
