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

<!-- Profile Leave tab: one member's balances and ledger for the current
     leave year. HR (leave:configure) can adjust balances and recalculate
     a frozen allocation. -->
<template>
  <section>
    <v-progress-linear v-if="balances.loading.value" indeterminate color="primary" class="mb-4" />
    <AppCallout v-if="balances.error.value" variant="error" class="mb-4">{{ balances.error.value }}</AppCallout>
    <template v-if="data">
      <div class="d-flex align-center justify-space-between flex-wrap ga-3 mb-4">
        <div class="text-body-2 text-medium-emphasis">
          {{ data.policy_name }} · Leave year {{ formatLeaveYear(data.leave_year) }}
        </div>
        <div v-if="canChangeBalance && data.balances.length" class="d-flex ga-2">
          <v-btn variant="text" size="small" prepend-icon="mdi-calculator-variant" @click="recalculating = true">
            Recalculate
          </v-btn>
          <v-btn variant="tonal" size="small" prepend-icon="mdi-plus-minus-variant" @click="adjusting = true">
            Adjust balance
          </v-btn>
        </div>
      </div>
      <p v-if="!data.balances.length" class="text-body-2 text-medium-emphasis mb-4">
        This policy has no leave types yet.
      </p>
      <BalanceGrid v-else :balances="data.balances" class="mb-6" />
      <h3 class="text-subtitle-2 font-weight-bold mb-2">Ledger</h3>
      <LedgerTable :entries="data.ledger" :balances="data.balances" />
      <AdjustBalanceDialog
        v-model="adjusting"
        :balances="data.balances"
        :leave-year="data.leave_year.label"
        :save="body => balances.adjust(userId, body)"
      />
      <RecalculateDialog
        v-model="recalculating"
        :balances="data.balances"
        :leave-year="data.leave_year.label"
        :recalculate="body => balances.recalculate(userId, body)"
      />
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AdjustBalanceDialog from '@/components/leave/AdjustBalanceDialog.vue'
import BalanceGrid from '@/components/leave/BalanceGrid.vue'
import LedgerTable from '@/components/leave/LedgerTable.vue'
import RecalculateDialog from '@/components/leave/RecalculateDialog.vue'
import { useMemberBalances } from '@/composables/useMemberBalances'
import { usePermissions } from '@/composables/usePermissions'
import { useAuthStore } from '@/stores/auth'
import { formatLeaveYear } from '@/utils/leaveDates'
import { canChangeMemberPolicy } from '@/utils/policyMembers'

const props = defineProps<{ userId: string }>()

const { canConfigureLeave, isOrgOwner } = usePermissions()
const authStore = useAuthStore()
// Nobody but the owner changes their own balance (the API refuses it).
const canChangeBalance = computed(
  () =>
    canConfigureLeave.value &&
    canChangeMemberPolicy(props.userId, authStore.user?.id, isOrgOwner.value),
)
const balances = useMemberBalances()
const data = computed(() => balances.data.value)
const adjusting = ref(false)
const recalculating = ref(false)

watch(() => props.userId, id => void balances.load(id), { immediate: true })
</script>
