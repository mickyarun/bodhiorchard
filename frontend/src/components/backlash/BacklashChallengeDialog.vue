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
<template>
  <v-dialog :model-value="modelValue" max-width="580" @update:model-value="setOpen">
    <section class="challenge" aria-labelledby="backlash-challenge-title">
      <header class="challenge__hero">
        <div class="challenge__mark" aria-hidden="true">
          <span class="challenge__piece challenge__piece--black" />
          <span class="challenge__piece challenge__piece--white" />
        </div>
        <div>
          <div class="challenge__eyebrow">TACTICAL DUEL · 2 PLAYERS</div>
          <h2 id="backlash-challenge-title">Start a Backlash match</h2>
          <p>Choose one teammate. White moves first; colours are assigned when both players join.</p>
        </div>
      </header>

      <v-alert v-if="error" type="error" density="compact" class="mx-6 mt-4">
        {{ error }}
      </v-alert>

      <div class="challenge__rules" aria-label="Quick rules">
        <span><strong>Overlings</strong> jump and chain-capture</span>
        <span><strong>Underlings</strong> capture diagonally</span>
        <span><strong>60 s</strong> per turn</span>
      </div>

      <div class="challenge__body">
        <div class="challenge__label">
          <span>Choose opponent</span>
          <span>{{ selectedIds.length }}/1</span>
        </div>
        <div class="challenge__members">
          <MemberPicker
            v-model="selectedIds"
            :members="opponents"
            :max-selection="1"
            :loading="loading"
            empty-message="No other members are available in your organisation."
          />
        </div>
      </div>

      <footer class="challenge__footer">
        <v-btn variant="text" :disabled="sending" @click="setOpen(false)">Cancel</v-btn>
        <button class="challenge__send" :disabled="!canSend" @click="sendChallenge">
          <v-progress-circular v-if="sending" indeterminate size="17" width="2" />
          <v-icon v-else icon="mdi-sword-cross" size="19" />
          {{ sending ? 'Creating room…' : 'Send challenge' }}
        </button>
      </footer>
    </section>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useMemberDirectory } from '@/composables/useMemberDirectory'
import { OrgRoomClient } from '@/multiplayer/OrgRoomClient'
import MemberPicker from '@/components/race/MemberPicker.vue'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [open: boolean] }>()

const router = useRouter()
const auth = useAuthStore()
const directory = useMemberDirectory()
const selectedIds = ref<string[]>([])
const sending = ref(false)
const error = ref('')

const loading = computed(() => directory.loading.value)
const opponents = computed(() => {
  const selfId = auth.user?.id
  const seen = new Set<string>()
  return directory.entries.value.filter((member) => {
    if (member.id === selfId || seen.has(member.id)) return false
    seen.add(member.id)
    return true
  })
})
const canSend = computed(() => selectedIds.value.length === 1 && !sending.value)

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    selectedIds.value = []
    error.value = ''
    void directory.ensureLoaded()
  },
  { immediate: true },
)

function setOpen(open: boolean): void {
  if (sending.value) return
  emit('update:modelValue', open)
}

async function sendChallenge(): Promise<void> {
  const user = auth.user
  const invitedUserId = selectedIds.value[0]
  if (!user || !auth.token || !invitedUserId || !canSend.value) {
    error.value = 'Choose an opponent and make sure you are signed in.'
    return
  }
  sending.value = true
  error.value = ''
  try {
    const client = OrgRoomClient.getInstance()
    if (!client.isConnected) {
      await client.connect(user.org_id, {
        userId: user.id,
        name: user.name,
        characterModel: user.character_model ?? undefined,
        token: auth.token,
      })
    }
    const { roomId } = await client.sendBacklashCreate({ invitedUserId })
    emit('update:modelValue', false)
    await router.push({ name: 'backlash-room', params: { roomId } })
  } catch (cause) {
    console.error('[BacklashChallengeDialog] challenge failed:', cause)
    error.value = cause instanceof Error ? cause.message : 'Could not create the challenge.'
  } finally {
    sending.value = false
  }
}
</script>

<style scoped>
.challenge {
  overflow: hidden;
  color: #fff8e8;
  border: 1px solid rgba(222, 160, 92, 0.38);
  border-radius: 22px;
  background: linear-gradient(155deg, #17110e, #3b1d18 68%, #6a2a20);
  box-shadow: 0 30px 80px rgba(0, 0, 0, 0.55);
}
.challenge__hero {
  display: flex;
  gap: 18px;
  align-items: center;
  padding: 25px 26px 18px;
  background: radial-gradient(circle at 80% 0, rgba(211, 119, 57, 0.22), transparent 48%);
}
.challenge__hero h2 { margin: 2px 0 4px; font-family: Georgia, serif; font-size: 28px; }
.challenge__hero p { margin: 0; color: rgba(255, 248, 232, 0.68); font-size: 13px; }
.challenge__eyebrow { color: #e6ac6a; font-size: 10px; font-weight: 800; letter-spacing: .18em; }
.challenge__mark { position: relative; width: 72px; height: 58px; flex: 0 0 auto; }
.challenge__piece {
  position: absolute; width: 45px; height: 45px; border-radius: 50%; border: 3px solid;
  box-shadow: inset 0 0 0 4px rgba(255,255,255,.08), 0 8px 15px rgba(0,0,0,.35);
}
.challenge__piece--black { left: 0; top: 0; background: #151515; border-color: #3d3834; }
.challenge__piece--white { right: 0; bottom: 0; background: #eee3cf; border-color: #fffaf0; }
.challenge__rules { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: rgba(255,255,255,.08); }
.challenge__rules span { padding: 10px 12px; background: rgba(18,11,8,.86); color: rgba(255,248,232,.67); font-size: 11px; text-align: center; }
.challenge__rules strong { display: block; color: #f3c994; }
.challenge__body { padding: 20px 26px 10px; }
.challenge__label { display: flex; justify-content: space-between; margin-bottom: 8px; color: #e8b97d; font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: .1em; }
.challenge__members { max-height: 260px; overflow-y: auto; border: 1px solid rgba(255,255,255,.08); border-radius: 12px; padding: 6px; background: rgba(0,0,0,.14); }
.challenge__footer { display: flex; justify-content: flex-end; gap: 10px; padding: 16px 26px 22px; }
.challenge__send { display: inline-flex; align-items: center; gap: 8px; min-width: 165px; justify-content: center; padding: 11px 18px; border: 0; border-radius: 10px; background: linear-gradient(135deg, #c85b33, #8e2c24); color: white; font-weight: 800; cursor: pointer; box-shadow: 0 8px 24px rgba(151,45,33,.35); }
.challenge__send:disabled { opacity: .45; cursor: not-allowed; box-shadow: none; }
@media (max-width: 520px) {
  .challenge__hero { align-items: flex-start; padding: 20px; }
  .challenge__mark { transform: scale(.8); transform-origin: left top; width: 58px; }
  .challenge__rules { grid-template-columns: 1fr; }
  .challenge__body, .challenge__footer { padding-left: 18px; padding-right: 18px; }
}
</style>
