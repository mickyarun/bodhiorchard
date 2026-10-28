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

<!-- Your photo on My details when HR hasn't set up your employee record:
     the photo belongs to your account, not the record, so it can still be
     added, replaced or removed here. -->
<template>
  <section v-if="auth.user" class="own-photo" aria-labelledby="own-photo-title">
    <EmployeeAvatar
      :user-id="auth.user.id"
      :name="auth.user.name"
      :avatar-url="auth.user.avatar_url"
      editable
      @updated="onUpdated"
      @error="error = $event"
    />
    <div class="own-photo__text">
      <h2 id="own-photo-title" class="own-photo__name">{{ auth.user.name }}</h2>
      <p class="own-photo__hint">Your photo shows next to your name across Glideship.</p>
      <AppCallout v-if="error" variant="error" class="mt-2">{{ error }}</AppCallout>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import EmployeeAvatar from '@/components/people/EmployeeAvatar.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const error = ref('')

function onUpdated(avatarUrl: string | null): void {
  error.value = ''
  auth.setAvatarUrl(avatarUrl)
}
</script>

<style scoped>
.own-photo {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: var(--radius-card);
  background: rgb(var(--v-theme-surface));
}
.own-photo__text {
  min-width: 0;
}
.own-photo__name {
  margin: 0;
  font-size: var(--text-md);
  font-weight: 600;
}
.own-photo__hint {
  margin: 2px 0 0;
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
