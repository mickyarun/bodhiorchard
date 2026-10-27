// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// The open BUD's timeline events. They feed the Activity panel and the
// Closed tab, and reload after anything that writes an event.

import { ref, type ComputedRef } from 'vue'
import { useBUDStore } from '@/stores/bud'
import type { BUDDocument, TimelineEvent } from '@/types'

export function useBudTimeline(bud: ComputedRef<BUDDocument | null>) {
  const budStore = useBUDStore()
  const timelineEvents = ref<TimelineEvent[]>([])
  const timelineLoading = ref(false)

  async function loadTimeline(): Promise<void> {
    if (!bud.value) return
    timelineLoading.value = true
    timelineEvents.value = await budStore.fetchTimeline(bud.value.id)
    timelineLoading.value = false
  }

  return { timelineEvents, timelineLoading, loadTimeline }
}
