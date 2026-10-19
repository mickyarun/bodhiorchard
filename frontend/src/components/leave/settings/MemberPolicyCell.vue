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

<!-- The policy someone follows; a "Default" badge when nobody assigned it. -->
<template>
  <span class="d-inline-flex align-center ga-2">
    <span>{{ member.policy_name }}</span>
    <v-tooltip v-if="!member.explicit" :text="IMPLICIT_POLICY_HINT" location="top">
      <template #activator="{ props: tip }">
        <v-chip v-bind="tip" size="x-small" color="primary" variant="tonal" label tabindex="0" :aria-label="`Default: ${IMPLICIT_POLICY_HINT}`">
          Default
        </v-chip>
      </template>
    </v-tooltip>
  </span>
</template>

<script setup lang="ts">
import type { PolicyMemberRead } from '@/types/leavePolicy'
import { IMPLICIT_POLICY_HINT } from '@/utils/policyMembers'

defineProps<{ member: PolicyMemberRead }>()
</script>
