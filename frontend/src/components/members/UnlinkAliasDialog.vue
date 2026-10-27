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

<!-- Confirm removing a linked email alias from a member. -->
<template>
  <v-dialog v-model="open" max-width="440">
    <v-card>
      <v-card-title>Unlink alias</v-card-title>
      <v-card-text>
        Remove <strong>{{ email }}</strong> from <strong>{{ member?.name }}</strong>? The next scan treats
        commits from this email as a separate person unless you merge them again.
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="open = false">Cancel</v-btn>
        <v-btn color="error" variant="flat" :loading="unlinking" @click="submit">Unlink</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useMembersStore, type Member } from '@/stores/members'

const props = defineProps<{ member: Member | null; email: string }>()
const open = defineModel<boolean>({ required: true })
const store = useMembersStore()
const unlinking = ref(false)

async function submit(): Promise<void> {
  if (!props.member) return
  unlinking.value = true
  const ok = await store.unlinkAlias(props.member.id, props.email)
  unlinking.value = false
  if (ok) open.value = false
}
</script>
