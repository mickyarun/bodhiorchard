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

<!-- Balance cards for every leave type, plus optional holidays when the
     policy gives any. Used on Leave home, the profile Leave tab and, compact,
     on approval cards (with the requested type highlighted). -->
<template>
  <div class="balance-grid" :class="{ 'balance-grid--compact': compact }">
    <BalanceCard v-for="card in cards" :key="card.key" v-bind="card.props" :compact="compact" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import BalanceCard from '@/components/leave/BalanceCard.vue'
import type { Balance, Decimalish, OptionalHolidayBalance } from '@/types/leave'
import {
  balanceCaption,
  formatDays,
  meterPercents,
  pluralDays,
  swatchColor,
  toNumber,
} from '@/utils/leave'
import { bookedAheadNote, earningCaption, monthlyLimitNote } from '@/utils/leaveAccrual'

const props = defineProps<{
  balances: Balance[]
  optional?: OptionalHolidayBalance | null
  /** Loss-of-pay days this leave year; a card shows when there are any. */
  lopDays?: Decimalish | null
  compact?: boolean
  /** A leave type to mark, e.g. the one being requested. */
  highlightTypeId?: string | null
}>()

function leaveCard(balance: Balance) {
  const meter = meterPercents(balance)
  const available = toNumber(balance.available)
  const highlight = balance.leave_type.id === props.highlightTypeId
  return {
    key: balance.leave_type.id,
    props: {
      title: balance.leave_type.name,
      color: swatchColor(balance.leave_type.color_key),
      value: meter ? formatDays(available) : 'No limit',
      unit: meter ? (available === 1 ? 'day left' : 'days left') : '',
      meter,
      caption: meter
        ? (earningCaption(balance) ?? balanceCaption(balance))
        : `${pluralDays(toNumber(balance.used))} taken`,
      note: monthlyLimitNote(balance) || bookedAheadNote(balance),
      tag: highlight ? 'This request' : balance.is_paid ? '' : 'Unpaid',
      highlight,
    },
  }
}

function optionalCard(optional: OptionalHolidayBalance) {
  const percent = (n: number) => (optional.quota ? Math.min(100, (n / optional.quota) * 100) : 0)
  const used = percent(optional.used)
  return {
    key: 'optional-holidays',
    props: {
      title: 'Optional holidays',
      color: 'secondary',
      value: `${optional.remaining} of ${optional.quota}`,
      unit: 'left',
      meter: { used, pending: Math.min(100 - used, percent(optional.pending)) },
      caption:
        optional.pending > 0
          ? `${optional.used} used · ${optional.pending} pending`
          : `${optional.used} used`,
      tag: '',
      note: '',
      highlight: false,
    },
  }
}

function lopCard(days: number) {
  return {
    key: 'loss-of-pay',
    props: {
      title: 'Loss of pay',
      color: 'warning',
      value: formatDays(days),
      unit: days === 1 ? 'day' : 'days',
      meter: null,
      caption: 'Leave past your balance this year',
      tag: 'Unpaid',
      note: '',
      highlight: false,
    },
  }
}

const cards = computed(() => {
  const list = props.balances.map(leaveCard)
  if (props.optional && props.optional.quota > 0) list.push(optionalCard(props.optional))
  const lop = toNumber(props.lopDays)
  if (lop > 0) list.push(lopCard(lop))
  return list
})
</script>

<style scoped>
.balance-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}
.balance-grid--compact {
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
}
</style>
